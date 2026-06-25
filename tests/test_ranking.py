#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for :mod:`scripts.ranking` (RRF merge + normalisation).

Covers:
- Basic correctness (single source, two sources, overlap, no overlap).
- Determinism (stable tie-break by key).
- Multi-hit handling (same key from same source twice → list, not overwrite).
- Edge cases (empty input, all-zero scores, k validation, missing 'key').
- :func:`normalize_scores` mathematical contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Local package — keep the sys.path nudge consistent with sibling tests.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ranking import (  # noqa: E402  pylint: disable=wrong-import-position
    DEFAULT_K,
    RankedResult,
    make_join_key,
    normalize_existing_key,
    normalize_scores,
    rrf_merge,
)


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------


def test_single_source_preserves_order():
    """One stream alone should produce results in input order."""
    fts = [
        {"key": "alpha.md", "snippet": "first"},
        {"key": "beta.md", "snippet": "second"},
        {"key": "gamma.md", "snippet": "third"},
    ]
    merged = rrf_merge(("fts", fts))

    assert [r.key for r in merged] == ["alpha.md", "beta.md", "gamma.md"]
    # Score must strictly decrease since ranks are unique.
    scores = [r.score for r in merged]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1]


def test_two_sources_with_full_overlap():
    """Same keys in both streams → scores combine, top-1 dominates."""
    fts = [{"key": "a.md"}, {"key": "b.md"}]
    sem = [{"key": "a.md"}, {"key": "b.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert len(merged) == 2
    assert merged[0].key == "a.md"
    # a.md gets rank 1 from both streams, b.md gets rank 2 from both.
    expected_a = 2 * (1.0 / (DEFAULT_K + 1))
    expected_b = 2 * (1.0 / (DEFAULT_K + 2))
    assert merged[0].score == pytest.approx(expected_a)
    assert merged[1].score == pytest.approx(expected_b)


def test_two_sources_with_no_overlap():
    """Disjoint streams → all results retained, sorted by RRF rank-1 score."""
    fts = [{"key": "x.md"}]
    sem = [{"key": "y.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert len(merged) == 2
    # Both at rank 1 → same RRF score → tie-break by key.
    assert merged[0].key == "x.md"
    assert merged[1].key == "y.md"
    assert merged[0].score == pytest.approx(merged[1].score)


def test_partial_overlap_promotes_overlapping_key():
    """Key in both streams should outrank keys present in only one."""
    fts = [{"key": "shared.md"}, {"key": "fts_only.md"}]
    sem = [{"key": "sem_only.md"}, {"key": "shared.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert merged[0].key == "shared.md"
    assert merged[0].score > merged[1].score


# ---------------------------------------------------------------------------
# Determinism — flaky-test prevention (Stability test from the design review)
# ---------------------------------------------------------------------------


def test_stable_ordering_reproduces_across_runs():
    """Same input must produce identical output across repeated calls."""
    fts = [{"key": "a.md"}, {"key": "b.md"}, {"key": "c.md"}]
    sem = [{"key": "c.md"}, {"key": "a.md"}, {"key": "b.md"}]

    run1 = rrf_merge(("fts", fts), ("semantic", sem))
    run2 = rrf_merge(("fts", fts), ("semantic", sem))

    assert [r.key for r in run1] == [r.key for r in run2]
    assert [r.score for r in run1] == [r.score for r in run2]


def test_tied_scores_break_by_lexicographic_key():
    """When two keys have identical RRF score, sort by key ascending."""
    # Both at rank 1 in their respective streams → identical RRF score.
    fts = [{"key": "zebra.md"}]
    sem = [{"key": "alpha.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert merged[0].key == "alpha.md"
    assert merged[1].key == "zebra.md"


# ---------------------------------------------------------------------------
# Multi-hit handling — sources stored as list, never overwritten
# ---------------------------------------------------------------------------


def test_same_key_twice_in_one_source_records_both_hits():
    """If the same key appears at multiple ranks in one source, keep both."""
    fts = [
        {"key": "handoff.md", "snippet": "chunk 1", "bm25": 0.9},
        {"key": "decisions.md", "snippet": "other"},
        {"key": "handoff.md", "snippet": "chunk 2", "bm25": 0.5},
    ]

    merged = rrf_merge(("fts", fts))
    handoff = next(r for r in merged if r.key == "handoff.md")

    assert len(handoff.sources["fts"]) == 2
    snippets = [hit["snippet"] for hit in handoff.sources["fts"]]
    assert "chunk 1" in snippets
    assert "chunk 2" in snippets
    # Both contributions should be summed into total score.
    expected = 1.0 / (DEFAULT_K + 1) + 1.0 / (DEFAULT_K + 3)
    assert handoff.score == pytest.approx(expected)


def test_per_source_payload_excludes_key_includes_rank_and_contribution():
    """Each per-source hit records original metadata + rank + RRF contribution."""
    fts = [{"key": "a.md", "snippet": "hi", "bm25": 0.7}]
    merged = rrf_merge(("fts", fts))

    payload = merged[0].sources["fts"][0]
    assert "key" not in payload  # promoted to top-level RankedResult
    assert payload["snippet"] == "hi"
    assert payload["bm25"] == 0.7
    assert payload["rank"] == 1
    assert payload["rrf_contribution"] == pytest.approx(1.0 / (DEFAULT_K + 1))


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_streams_produce_empty_result():
    """Both streams empty → empty list, no exception."""
    assert rrf_merge(("fts", []), ("semantic", [])) == []


def test_one_empty_stream_falls_back_to_other():
    """Empty FTS + non-empty semantic should rank semantic-only correctly."""
    sem = [{"key": "only.md"}]
    merged = rrf_merge(("fts", []), ("semantic", sem))

    assert len(merged) == 1
    assert merged[0].key == "only.md"
    assert merged[0].score == pytest.approx(1.0 / (DEFAULT_K + 1))


def test_negative_k_raises():
    """Defensive: negative k makes no mathematical sense for RRF."""
    with pytest.raises(ValueError, match="non-negative"):
        rrf_merge(("fts", [{"key": "a.md"}]), k=-1)


def test_missing_key_in_item_raises():
    """A stream item without 'key' is a programming error — fail loud."""
    with pytest.raises(ValueError, match="missing required 'key' field"):
        rrf_merge(("fts", [{"snippet": "no key here"}]))


def test_three_sources_extensible():
    """API is variadic — three streams should merge without changes."""
    a = [{"key": "doc.md"}]
    b = [{"key": "doc.md"}]
    c = [{"key": "doc.md"}]
    merged = rrf_merge(("a", a), ("b", b), ("c", c))

    assert len(merged) == 1
    assert set(merged[0].sources.keys()) == {"a", "b", "c"}
    assert merged[0].score == pytest.approx(3.0 / (DEFAULT_K + 1))


# ---------------------------------------------------------------------------
# normalize_scores
# ---------------------------------------------------------------------------


def test_normalize_scores_top_result_is_one():
    """Top hit's normalized_score must be exactly 1.0."""
    fts = [{"key": "a.md"}, {"key": "b.md"}]
    merged = normalize_scores(rrf_merge(("fts", fts)))

    assert merged[0].normalized_score == pytest.approx(1.0)
    assert 0.0 < merged[1].normalized_score < 1.0


def test_normalize_scores_empty_list_no_error():
    """Empty input must not crash."""
    assert normalize_scores([]) == []


def test_normalize_scores_all_zero_max_assigns_zero_to_all():
    """Edge case: if every score is 0.0, no division by zero."""
    results = [RankedResult(key="a"), RankedResult(key="b")]
    out = normalize_scores(results)

    assert all(r.normalized_score == 0.0 for r in out)


def test_normalize_scores_returns_same_list_for_chaining():
    """Mutates in place and returns the same list (caller convenience)."""
    fts = [{"key": "a.md"}]
    merged = rrf_merge(("fts", fts))
    out = normalize_scores(merged)

    assert out is merged


def test_normalize_scores_preserves_ordering():
    """Normalization must not reorder results."""
    fts = [{"key": "a.md"}, {"key": "b.md"}, {"key": "c.md"}]
    merged = rrf_merge(("fts", fts))
    keys_before = [r.key for r in merged]
    normalize_scores(merged)
    keys_after = [r.key for r in merged]

    assert keys_before == keys_after


# ---------------------------------------------------------------------------
# Cross-source key normalisation — guards against the silent-bug class
# where FTS stores ``my-app`` and ChromaDB stores ``my_app`` and RRF
# fails to merge them.
# ---------------------------------------------------------------------------


def test_make_join_key_global_passthrough():
    """``global`` is already alphanumeric and must round-trip unchanged."""
    assert make_join_key("global", "handoff.md") == "[global] handoff.md"


def test_make_join_key_normalises_hyphenated_source():
    """Project dir ``my-app`` must canonicalise to ``my_app``."""
    assert make_join_key("my-app", "decisions.md") == "[my_app] decisions.md"


def test_make_join_key_collapses_repeated_specials():
    """Multiple consecutive non-alnum chars collapse to a single ``_``."""
    assert make_join_key("a---b   c", "x.md") == "[a_b_c] x.md"


def test_make_join_key_strips_edge_underscores():
    """Leading/trailing non-alnum characters disappear (no empty bracket)."""
    assert make_join_key("--proj--", "x.md") == "[proj] x.md"


def test_make_join_key_empty_source():
    """Empty source produces empty bracket — caller's defensive contract."""
    assert make_join_key("", "f.md") == "[] f.md"


def test_make_join_key_fts_and_semantic_collide_after_normalisation():
    """Different raw forms of the same project must produce identical keys.

    This is the exact bug class ``ranking.py`` exists to prevent: FTS5
    stores the raw directory name while ChromaDB collection naming
    rules force underscores. Without normalisation, RRF would treat
    them as two separate documents.
    """
    fts_raw = "my-fancy-app"           # FTS5 stores raw dir name
    semantic_normalised = "my_fancy_app"  # ChromaDB collection name

    assert make_join_key(fts_raw, "x.md") == make_join_key(semantic_normalised, "x.md")


def test_normalize_existing_key_canonicalises_bracket():
    """``"[my-app] f.md"`` (raw) and ``"[my_app] f.md"`` (normalised)
    must converge to the same canonical string."""
    assert normalize_existing_key("[my-app] f.md") == normalize_existing_key("[my_app] f.md")


def test_normalize_existing_key_returns_input_on_unparseable():
    """Defensive: arbitrary strings without bracket prefix pass through."""
    assert normalize_existing_key("no brackets here") == "no brackets here"
    assert normalize_existing_key("") == ""


def test_normalize_existing_key_handles_nested_or_weird_filenames():
    """Filename portion is preserved verbatim — only the source bracket is touched."""
    assert (
        normalize_existing_key("[my-app] sub/dir/file with spaces.md")
        == "[my_app] sub/dir/file with spaces.md"
    )


def test_rrf_merges_after_cross_source_normalisation():
    """End-to-end: pre-normalised keys from two sources must merge into one entry."""
    fts = [{"key": normalize_existing_key("[my-app] handoff.md")}]
    semantic = [{"key": normalize_existing_key("[my_app] handoff.md")}]

    merged = rrf_merge(("fts", fts), ("semantic", semantic))

    assert len(merged) == 1
    assert merged[0].key == "[my_app] handoff.md"
    assert set(merged[0].sources.keys()) == {"fts", "semantic"}


# ---------------------------------------------------------------------------
# New guards: empty key, duplicate source, original_rank preservation
# ---------------------------------------------------------------------------


def test_empty_key_raises():
    """Empty string key is a programming error — fail loud."""
    with pytest.raises(ValueError, match="empty 'key'"):
        rrf_merge(("fts", [{"key": ""}]))


def test_whitespace_only_key_raises():
    """Whitespace-only key is effectively empty after strip."""
    with pytest.raises(ValueError, match="empty 'key'"):
        rrf_merge(("fts", [{"key": "   "}]))


def test_duplicate_source_name_raises():
    """Two streams with the same name is ambiguous — fail loud."""
    with pytest.raises(ValueError, match="Duplicate source_name"):
        rrf_merge(("fts", [{"key": "a.md"}]), ("fts", [{"key": "b.md"}]))


def test_original_rank_preserved_when_item_has_rank_field():
    """If input item already has 'rank', it must be saved as 'original_rank'."""
    items = [{"key": "doc.md", "rank": 42, "bm25": 0.8}]
    merged = rrf_merge(("fts", items))

    payload = merged[0].sources["fts"][0]
    assert payload["original_rank"] == 42
    assert payload["rank"] == 1
    assert payload["bm25"] == 0.8


def test_no_original_rank_when_item_lacks_rank_field():
    """If input item has no 'rank' field, 'original_rank' must not appear."""
    items = [{"key": "doc.md", "bm25": 0.8}]
    merged = rrf_merge(("fts", items))

    payload = merged[0].sources["fts"][0]
    assert "original_rank" not in payload
    assert payload["rank"] == 1


# ---------------------------------------------------------------------------
# _validate_key_shape — chunk-level key detection
# ---------------------------------------------------------------------------


def test_validate_key_shape_warns_on_chunk_pattern(caplog):
    """Chunk-like keys trigger a warning (once per unique key)."""
    import logging

    items = [
        {"key": "file.md#chunk_3"},
        {"key": "file.md#chunk_3"},
    ]
    with caplog.at_level(logging.WARNING):
        rrf_merge(("fts", items))

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert len(warnings) == 1


def test_validate_key_shape_no_warning_on_normal_key(caplog):
    """Normal document-level keys must not trigger warnings."""
    import logging

    items = [{"key": "[global] handoff.md"}]
    with caplog.at_level(logging.WARNING):
        rrf_merge(("fts", items))

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert len(warnings) == 0


@pytest.mark.parametrize(
    "chunk_key",
    [
        "file.md#chunk_3",      # markdown anchor / heading fragment
        "file.md:3",            # real on-disk format from l4_semantic_global.py
        "file.md?chunk=5",      # URL-style chunk selector
        "file.md&chunk=5",      # URL-style (ampersand variant)
        "file_chunk_0",         # snake_case chunk marker
    ],
)
def test_validate_key_shape_warns_on_all_chunk_formats(chunk_key, caplog):
    """Every chunk-id format emitted by the engines must be flagged.

    Regression guard for the extended _CHUNK_PATTERN: the real semantic
    indexer writes ``f"{md_file}:{i}"`` (l4_semantic_global.py:514), which
    the original narrow pattern ``(#\\w+|[?&]chunk=)`` missed entirely.
    """
    import logging
    import ranking as _ranking

    # Dedup set is module-level mutable state — clear it so that earlier
    # tests (e.g. test_validate_key_shape_warns_on_chunk_pattern) don't
    # suppress the warning for the same key.
    _ranking._SEEN_BAD_KEYS.clear()

    items = [{"key": chunk_key}]
    with caplog.at_level(logging.WARNING):
        rrf_merge(("fts", items))

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert len(warnings) == 1, f"chunk key not detected: {chunk_key!r}"


@pytest.mark.parametrize(
    "doc_key",
    [
        "[global] 2024-01-15-notes.md",   # date in filename — NOT a chunk id
        "[g] v2/changelog.md",            # version dir — NOT a chunk id
        "[proj] dir/sub.md",              # nested path
        "[global] handoff.md",            # plain doc
    ],
)
def test_validate_key_shape_no_false_positives_on_valid_doc_keys(doc_key, caplog):
    """Valid document-level keys (with dates/versions) must NOT be flagged.

    The ``:\\d+`` alternative in _CHUNK_PATTERN is anchored to the end of
    the key (``:\\d+$``) so that ``2024-01-15`` (digits mid-path) and
    ``v2/`` (digits glued to a slash) are not mistaken for a ``file:N``
    chunk suffix, which only ever appears at the very end of a key.
    """
    import logging

    items = [{"key": doc_key}]
    with caplog.at_level(logging.WARNING):
        rrf_merge(("fts", items))

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert len(warnings) == 0, f"false positive on valid key: {doc_key!r}"


def test_rrf_merge_strict_mode_rejects_chunk_key():
    """strict=True turns a chunk-level key into a hard ValueError."""
    items = [{"key": "[global] file.md:3"}]
    with pytest.raises(ValueError, match="chunk-level"):
        rrf_merge(("fts", items), strict=True)


def test_rrf_merge_strict_false_ignores_env_and_only_warns(caplog, monkeypatch):
    """strict=False overrides a strict env var back to warn-only."""
    import importlib
    import logging

    monkeypatch.setenv("RRF_STRICT_CHUNK_KEYS", "1")
    # Re-import the module-level default to pick up the env var.
    import ranking as ranking_mod
    importlib.reload(ranking_mod)

    items = [{"key": "[global] file.md:3"}]
    with caplog.at_level(logging.WARNING):
        # Call through the *reloaded* module to guarantee we hit the
        # fresh _STRICT_CHUNK_KEYS value (True from env).
        # Explicit strict=False must still win over the env-enabled default.
        ranking_mod.rrf_merge(("fts", items), strict=False)

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert len(warnings) == 1, "strict=False should warn, not raise"


def test_validate_key_shape_no_false_positive_on_mid_filename_colon_digits(caplog):
    """Colon+digits *inside* a filename must NOT be flagged as chunk-level.

    Regression for the over-broad ``:\\d+\\b`` pattern: a document key whose
    filename legitimately contains ``:<digits>`` somewhere other than the
    very end (e.g. ``note:123.md``) was wrongly flagged as chunk-level. The
    ``:\\d+$`` anchor fixes this -- only a trailing ``:N`` (the real
    ``f"{md_file}:{i}"`` on-disk format) counts as a chunk suffix.
    """
    import logging
    import ranking as _ranking

    _ranking._SEEN_BAD_KEYS.clear()

    items = [
        {"key": "[global] note:123.md"},
        {"key": "[proj] v1:2-draft.md"},
        {"key": "[g] section:4-overview.md"},
    ]
    with caplog.at_level(logging.WARNING):
        rrf_merge(("fts", items))

    warnings = [r for r in caplog.records if "chunk-level" in r.message]
    assert warnings == [], f"false positive on mid-filename colon: {warnings!r}"


def test_rrf_merge_env_strict_raises_without_explicit_arg(monkeypatch):
    """RRF_STRICT_CHUNK_KEYS=1 alone makes a chunk key a hard error.

    Complements test_rrf_merge_strict_false_ignores_env_and_only_warns:
    that one proves an explicit strict=False overrides the env back to
    warn-only; this proves the env var is honoured when no explicit
    argument is passed (the CI / pre-commit enforcement path).
    """
    import importlib
    import ranking as ranking_mod

    monkeypatch.setenv("RRF_STRICT_CHUNK_KEYS", "1")
    importlib.reload(ranking_mod)
    try:
        items = [{"key": "[global] file.md:3"}]
        with pytest.raises(ValueError, match="chunk-level"):
            ranking_mod.rrf_merge(("fts", items))
    finally:
        # Restore the module-level default so later tests in the session
        # observe warn-only behaviour again.
        monkeypatch.delenv("RRF_STRICT_CHUNK_KEYS", raising=False)
        importlib.reload(ranking_mod)


# ---------------------------------------------------------------------------
# normalize_scores — inf protection
# ---------------------------------------------------------------------------


def test_normalize_scores_handles_inf_score():
    """If a score is somehow inf, normalization must not produce nan."""
    results = [RankedResult(key="a", score=float('inf')), RankedResult(key="b", score=1.0)]
    out = normalize_scores(results)

    assert all(r.normalized_score == 0.0 for r in out)
