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
