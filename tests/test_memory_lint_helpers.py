"""
Tests for memory_lint_helpers.EncodingGate.

Cover the four public surfaces of the gate:

* ``assert_clean(text)`` — refuses cp1251-as-utf8 mojibake and U+FFFD.
* ``assert_clean_bytes(data)`` — also refuses non-UTF-8 byte input.
* ``scan_file(path)`` — non-raising audit used by ``--validate-encoding``.
* ``repair_mojibake(text)`` — round-trip recovery used by ``--repair-mojibake``.

The "real-world fixture" in :func:`MOJIBAKE_FRAGMENT` is taken verbatim
from a corrupted ``handoff.md`` produced by a Windows ``auto-remember``
hook that wrote subprocess output without re-decoding cp1251.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from memory_lint_helpers import (  # noqa: E402  pylint: disable=wrong-import-position
    EncodingError,
    EncodingGate,
)


# Real cp1251-as-utf8 mojibake observed in the wild.
# The original UTF-8 source was: "Рефакторинг 6 модулей: безопасность".
MOJIBAKE_FRAGMENT = (
    'Р\u00a0РµС„Р°РєС‚РѕСЂРёРЅРі 6 РјРѕРґСѓР»РµР№: '
    'Р±РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ'
)
RECOVERED_FRAGMENT = 'Рефакторинг 6 модулей: безопасность'


# Cyrillic-block-only mojibake: the original Russian word is composed
# of letters whose UTF-8 second byte produces a cp1251 glyph in
# U+0400..U+04FF (Cyrillic block) instead of U+0080..U+00BF (Latin-1
# supplement). The strict ``_MOJIBAKE_RE`` does NOT detect these on
# its own — only the broader ``_MOJIBAKE_RUN_RE`` does. Real samples
# from observed Windows ``auto-remember`` corruption.
CYRILLIC_BLOCK_MOJIBAKE_SAMPLES = [
    ('РёСЃС‚РѕСЂРёСЏ', 'история'),
    ('РіРѕСЂРѕРґ', 'город'),
    ('РјРёСЂ', 'мир'),
]


# Legitimate uppercase Russian patterns that match the broader
# ``_MOJIBAKE_RUN_RE`` shape (two consecutive ``[Р|С] + cp1251-high-
# byte glyph`` pairs) but are NOT mojibake. They must be left alone
# by ``assert_clean`` and ``scan_file`` thanks to the cp1251
# round-trip false-positive filter.
LEGITIMATE_UPPERCASE_RUSSIAN = [
    'СССР',          # Soviet Union — 2 pairs (СС, СР)
    'РОССИЯ',        # Russia, all caps — has 'РО','СС' run
    'СИСТЕМА',       # System — has 'СИ','СТ' run
    'СПАСИБО',       # Thank you, all caps — has 'СП','СИ' run
]


class TestAssertClean:
    def test_plain_ascii_passes(self):
        EncodingGate.assert_clean('Hello world: refactoring 6 modules.')

    def test_clean_cyrillic_passes(self):
        EncodingGate.assert_clean(RECOVERED_FRAGMENT)

    def test_clean_cyrillic_with_capital_r_and_s_passes(self):
        # Sanity: legitimate Russian words starting with Р/С followed by
        # a Cyrillic-block letter must NOT trigger the gate.
        EncodingGate.assert_clean(
            'Сергей пошёл в Республику Россия в 1991 году.'
        )

    def test_empty_string_passes(self):
        EncodingGate.assert_clean('')

    def test_replacement_character_rejected(self):
        with pytest.raises(EncodingError, match='U\\+FFFD'):
            EncodingGate.assert_clean('something \ufffd broken')

    def test_real_mojibake_rejected(self):
        with pytest.raises(EncodingError, match='cp1251'):
            EncodingGate.assert_clean(MOJIBAKE_FRAGMENT, source='handoff.md')

    def test_mojibake_fragment_inside_clean_text_rejected(self):
        # Even a single mojibake pair inside otherwise clean text must
        # be caught — hooks should never silently emit garbage.
        text = 'Some clean ASCII PLUS Р°Р±РІР· hidden mojibake.'
        with pytest.raises(EncodingError):
            EncodingGate.assert_clean(text)

    def test_source_label_included_in_error(self):
        with pytest.raises(EncodingError, match='git log subprocess'):
            EncodingGate.assert_clean(
                MOJIBAKE_FRAGMENT, source='git log subprocess'
            )

    @pytest.mark.parametrize(
        'mojibake,recovered', CYRILLIC_BLOCK_MOJIBAKE_SAMPLES
    )
    def test_cyrillic_block_only_mojibake_rejected(
        self, mojibake: str, recovered: str
    ):
        # Words like "история" / "город" / "мир" produce mojibake
        # whose second char of every pair is a Cyrillic-block glyph
        # (U+0400..U+04FF), not a Latin-1 supplement char. The strict
        # _MOJIBAKE_RE alone misses these; the broader _MOJIBAKE_RUN_RE
        # (gated by cp1251 round-trip) catches them. Without this
        # path, --validate-encoding would silently report these files
        # as clean.
        del recovered  # unused; round-trip is exercised in TestRepairMojibake
        with pytest.raises(EncodingError, match='mojibake'):
            EncodingGate.assert_clean(mojibake, source='hook')

    @pytest.mark.parametrize('text', LEGITIMATE_UPPERCASE_RUSSIAN)
    def test_legitimate_uppercase_russian_passes(self, text: str):
        # Uppercase Russian words / acronyms like СССР, РОССИЯ,
        # СИСТЕМА match the broader regex shape but fail the cp1251
        # round-trip (their cp1251 byte sequences aren't valid UTF-8),
        # so the gate must NOT flag them. Without the round-trip
        # check, all-caps Russian text would be falsely rejected.
        EncodingGate.assert_clean(text)


class TestAssertCleanBytes:
    def test_valid_utf8_bytes_round_trip(self):
        result = EncodingGate.assert_clean_bytes(
            RECOVERED_FRAGMENT.encode('utf-8')
        )
        assert result == RECOVERED_FRAGMENT

    def test_invalid_utf8_rejected(self):
        # cp1251-encoded Cyrillic is NOT valid UTF-8; gate must reject
        # the bytes before they get a chance to be silently written.
        with pytest.raises(EncodingError, match='not valid UTF-8'):
            EncodingGate.assert_clean_bytes(
                RECOVERED_FRAGMENT.encode('cp1251')
            )

    def test_mojibake_inside_valid_utf8_bytes_rejected(self):
        # Mojibake'd text is itself valid UTF-8 (every char is a real
        # Unicode code point), so the byte-level check passes; the
        # text-level check must still catch it.
        with pytest.raises(EncodingError, match='cp1251'):
            EncodingGate.assert_clean_bytes(
                MOJIBAKE_FRAGMENT.encode('utf-8'), source='subprocess'
            )


class TestScanFile:
    def test_clean_file_returns_none(self, tmp_path: Path):
        f = tmp_path / 'clean.md'
        f.write_text(RECOVERED_FRAGMENT, encoding='utf-8')
        assert EncodingGate.scan_file(f) is None

    def test_mojibake_file_returns_message(self, tmp_path: Path):
        f = tmp_path / 'broken.md'
        f.write_text(MOJIBAKE_FRAGMENT, encoding='utf-8')
        result = EncodingGate.scan_file(f)
        assert result is not None
        assert 'mojibake' in result

    def test_replacement_char_file_returns_message(self, tmp_path: Path):
        f = tmp_path / 'replaced.md'
        f.write_text('text \ufffd more', encoding='utf-8')
        result = EncodingGate.scan_file(f)
        assert result is not None
        assert 'U+FFFD' in result

    def test_non_utf8_file_returns_message(self, tmp_path: Path):
        f = tmp_path / 'cp1251.md'
        f.write_bytes(RECOVERED_FRAGMENT.encode('cp1251'))
        result = EncodingGate.scan_file(f)
        assert result is not None
        assert 'UTF-8' in result

    def test_missing_file_returns_none(self, tmp_path: Path):
        # No file -> scanner returns None silently (it's an audit
        # tool, not a presence checker).
        assert EncodingGate.scan_file(tmp_path / 'no-such.md') is None

    @pytest.mark.parametrize(
        'mojibake,recovered', CYRILLIC_BLOCK_MOJIBAKE_SAMPLES
    )
    def test_cyrillic_block_only_mojibake_file_returns_message(
        self, tmp_path: Path, mojibake: str, recovered: str
    ):
        # Regression for Devin Review finding
        # BUG_pr-review-job-15dd253a31bc4c8190d55ac467e80ab2_0001:
        # files containing only cyrillic-block mojibake (история,
        # город, мир) were silently reported as clean by --validate-
        # encoding before the broader detector + round-trip filter.
        del recovered  # exercised in TestRepairMojibake
        f = tmp_path / 'broken.md'
        f.write_text(mojibake, encoding='utf-8')
        result = EncodingGate.scan_file(f)
        assert result is not None
        assert 'mojibake' in result

    @pytest.mark.parametrize('text', LEGITIMATE_UPPERCASE_RUSSIAN)
    def test_legitimate_uppercase_russian_file_returns_none(
        self, tmp_path: Path, text: str
    ):
        # Uppercase Russian acronyms / words must NOT trigger the
        # scanner. They match the broader regex shape but fail the
        # cp1251 round-trip — the round-trip filter is the only thing
        # keeping them from being falsely reported.
        f = tmp_path / 'clean.md'
        f.write_text(text, encoding='utf-8')
        assert EncodingGate.scan_file(f) is None


class TestRepairMojibake:
    def test_repairs_real_handoff_fragment(self):
        recovered, ok = EncodingGate.repair_mojibake(MOJIBAKE_FRAGMENT)
        assert ok is True
        assert recovered == RECOVERED_FRAGMENT

    def test_repairs_mixed_clean_and_mojibake(self):
        # File with clean markdown header + mojibake'd body — the
        # most common shape produced by Windows ``auto-remember``
        # hooks.
        text = (
            f'**Сообщение:** {MOJIBAKE_FRAGMENT}\n\nClean trailing line.\n'
        )
        recovered, ok = EncodingGate.repair_mojibake(text)
        assert ok is True
        assert RECOVERED_FRAGMENT in recovered
        assert '**Сообщение:**' in recovered  # clean prefix preserved
        assert 'Clean trailing line.' in recovered  # clean suffix preserved

    def test_clean_text_passes_through_unchanged(self):
        recovered, ok = EncodingGate.repair_mojibake(RECOVERED_FRAGMENT)
        assert ok is False
        assert recovered == RECOVERED_FRAGMENT

    def test_pure_ascii_passes_through_unchanged(self):
        text = 'Just an ASCII sentence with no Cyrillic at all.'
        recovered, ok = EncodingGate.repair_mojibake(text)
        assert ok is False
        assert recovered == text

    def test_legitimate_russian_with_p_and_s_passes_unchanged(self):
        text = 'Сергей и Россия в Республике существовали до 1991 года.'
        recovered, ok = EncodingGate.repair_mojibake(text)
        assert ok is False
        assert recovered == text

    def test_repair_is_idempotent(self):
        # Repairing already-repaired text must be a no-op (no double
        # round-trip catastrophe).
        once, ok1 = EncodingGate.repair_mojibake(MOJIBAKE_FRAGMENT)
        twice, ok2 = EncodingGate.repair_mojibake(once)
        assert ok1 is True
        assert ok2 is False
        assert once == twice == RECOVERED_FRAGMENT
