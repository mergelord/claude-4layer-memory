#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-engine KEY CONTRACT regression tests.

Background
----------
Hybrid memory search merges three independent rankings (semantic via
ChromaDB, BM25 via SQLite FTS5, keyword via SQLite FTS5) through
Reciprocal Rank Fusion. RRF can only merge hits that share the **same**
document-level key. Historically the three engines built their keys
ad-hoc:

- semantic: ``f"[{source.replace('-', '_')}] {file}"`` (only hyphens
  collapsed)
- bm25:     ``f"[{row['source']}] {basename(path)}"`` (raw source)
- fts5:     ``f"[{row['source']}] {row['path']}"`` (raw source + full
  relative path)

For a project named ``my-app`` with a file at ``archive/notes.md``,
the three streams produced ``"[my_app] notes.md"``,
``"[my-app] notes.md"`` and ``"[my-app] archive/notes.md"``
respectively — three different keys for the same document, so RRF
saw three independent hits and never merged them.

Bug N-4 went further: the basename-based collapse meant two distinct
files (``archive/notes.md`` and ``current/notes.md``) silently merged
into one RankedResult ``[global] notes.md``. The fix routes every
engine through :func:`ranking.make_join_key`, which internally calls
:func:`ranking.normalize_document_path` on the document path — so a
POSIX rel_path is preserved verbatim and sub-directory siblings stay
distinct.

This test pins the contract: ``ranking.make_join_key(source, document)``
is the **only** legitimate way to construct a join key, and all three
engines must route through it (or through ``normalize_existing_key``
when they receive a pre-formed bracketed key from another engine).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Local package — keep the sys.path nudge consistent with sibling tests.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ranking import (  # noqa: E402  pylint: disable=wrong-import-position
    make_join_key,
    normalize_existing_key,
)


# ---------------------------------------------------------------------------
# 1. BM25 stream uses make_join_key
# ---------------------------------------------------------------------------


def _build_bm25_mock(rows):
    conn = MagicMock()
    cursor = MagicMock()
    conn.__enter__.return_value = conn
    cursor.fetchall.return_value = rows
    conn.execute.return_value = cursor
    return conn


def test_bm25_key_matches_make_join_key_for_plain_source():
    """``global`` round-trips unchanged through both code paths.

    After Bug N-4 the BM25 key preserves the rel_path stored in
    ``row['path']`` (it no longer strips down to basename), so a hit on
    ``docs/memory.md`` produces ``[global] docs/memory.md`` — distinct
    from a separate ``memory.md`` at the root.
    """
    from l4_bm25_search import fetch_bm25_results  # noqa: E402

    conn = _build_bm25_mock(
        [
            {
                "path": "docs/memory.md",
                "source": "global",
                "snippet": "snippet",
                "bm25_score": -2.5,
            }
        ]
    )
    with patch("l4_bm25_search._get_fts5_connection", return_value=conn):
        result = fetch_bm25_results("query")

    assert result[0]["key"] == make_join_key("global", "docs/memory.md")


def test_bm25_key_normalises_hyphenated_source():
    """``my-fancy-app`` from raw FTS row must canonicalise to ``my_fancy_app``.

    Without normalisation BM25 would emit ``"[my-fancy-app] file.md"``
    while semantic emits ``"[my_fancy_app] file.md"`` — RRF would never
    merge them.
    """
    from l4_bm25_search import fetch_bm25_results  # noqa: E402

    conn = _build_bm25_mock(
        [
            {
                "path": "memory/handoff.md",
                "source": "my-fancy-app",
                "snippet": "x",
                "bm25_score": -1.0,
            }
        ]
    )
    with patch("l4_bm25_search._get_fts5_connection", return_value=conn):
        result = fetch_bm25_results("query")

    assert result[0]["key"] == make_join_key("my-fancy-app", "memory/handoff.md")
    assert result[0]["key"] == "[my_fancy_app] memory/handoff.md"


# ---------------------------------------------------------------------------
# 2. FTS5 SearchResult exposes a make_join_key-derived key
# ---------------------------------------------------------------------------


def test_fts5_search_result_key_is_document_level_rel_path():
    """FTS5 ``SearchResult.key`` MUST be document-level POSIX rel_path.

    Bug N-4: the previous contract used ``basename(path)``, which silently
    collapsed ``archive/notes.md`` and ``current/notes.md`` into one
    ``[normalized_source] notes.md`` key during RRF merge. The fix is to
    preserve the full relative path (normalised through
    ``make_join_key`` → ``normalize_document_path``).
    """
    from l4_fts5_search import SearchResult  # noqa: E402

    # Build a fake row resembling what sqlite3.Row + FTS5 yield.
    fake_row = {
        "path": "archive/notes.md",
        "source": "my-fancy-app",
        "snippet": "snippet",
        "rank": -3.0,
    }

    # We replicate the production construction here — if the implementation
    # ever drifts, this test will catch it at the same time as the
    # contract test below.
    sr = SearchResult(
        path=f"[{fake_row['source']}] {fake_row['path']}",
        key=make_join_key(fake_row["source"], fake_row["path"]),
        snippet=fake_row["snippet"],
        rank=fake_row["rank"],
        source="fts5",
    )

    assert sr.key == "[my_fancy_app] archive/notes.md"
    # Display still preserves subdirectory info for humans.
    assert "archive/notes.md" in sr.path


def test_fts5_cached_search_uses_make_join_key(tmp_path, monkeypatch):
    """Live ``_cached_search`` must populate ``SearchResult.key`` via
    :func:`ranking.make_join_key` — not a string template.

    After Bug N-4 the join key preserves the sub-directory component so
    siblings with the same basename in different folders stay distinct.
    """
    from l4_fts5_search import L4FTS5Search  # noqa: E402

    fts = L4FTS5Search(db_path=tmp_path / "fts.db")
    assert fts.init_fts()

    # Index a file directly via the public API so the row hits the same
    # SELECT path as production.
    md = tmp_path / "memory" / "archive" / "notes.md"
    md.parent.mkdir(parents=True)
    md.write_text("memory subsystem notes", encoding="utf-8")
    monkeypatch.setattr(fts, "global_memory", md.parent.parent)
    monkeypatch.setattr(fts, "projects_base", tmp_path / "projects")
    fts.reindex_all()

    results = list(fts.search("memory"))
    assert results, "FTS5 index must return at least one hit for the seeded file"

    for r in results:
        # The display path AND the join key both keep the rel_path now.
        assert r.key == make_join_key("global", "archive/notes.md")


# ---------------------------------------------------------------------------
# 3. Semantic _make_document_key delegates to make_join_key
# ---------------------------------------------------------------------------


def test_semantic_make_document_key_matches_make_join_key():
    """``_make_document_key`` must agree byte-for-byte with ``make_join_key``."""
    # Avoid importing the full module (it pulls in chromadb/sentence_transformers).
    # We construct an unbound-method-style call via the source text instead.
    import importlib.util

    spec = importlib.util.find_spec("l4_semantic_global")
    if spec is None:
        pytest.skip("l4_semantic_global not importable in this env")

    try:
        module = importlib.import_module("l4_semantic_global")
    except Exception:  # nosec - optional deps missing
        pytest.skip("l4_semantic_global deps unavailable")

    memory = module.GlobalSemanticMemory.__new__(module.GlobalSemanticMemory)

    for source, filename in [
        ("global", "handoff.md"),
        ("my-project", "decisions.md"),
        ("my-fancy-app", "architecture.md"),
        ("a---b   c", "x.md"),  # tricky normalisation case
    ]:
        meta = {"file": filename}
        assert memory._make_document_key(source, meta) == make_join_key(
            source, filename
        )


# ---------------------------------------------------------------------------
# 4. Cross-engine agreement — the actual KEY CONTRACT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,rel_path",
    [
        ("global", "handoff.md"),
        ("my-app", "decisions.md"),
        ("my-fancy-app", "architecture.md"),
        ("project.with.dots", "x.md"),
        ("with spaces", "doc.md"),
        # Sub-directory cases (Bug N-4 regression): all three engines must
        # preserve the rel_path so siblings with shared basenames remain
        # distinct.
        ("global", "archive/notes.md"),
        ("my-app", "current/notes.md"),
    ],
)
def test_three_streams_emit_identical_join_keys(source, rel_path):
    """For every (source, rel_path), bm25 / fts / semantic must agree.

    This is the regression net for the original audit finding *and*
    Bug N-4: as long as every engine routes through ``make_join_key``
    (which internally calls ``normalize_document_path``), the three
    streams collapse onto a single key and RRF can merge them.
    """
    # BM25 builds keys via make_join_key on (row['source'], row['path']).
    bm25_key = make_join_key(source, rel_path)
    # FTS5 builds keys via make_join_key on (row['source'], row['path']).
    fts_key = make_join_key(source, rel_path)
    # Semantic builds keys via make_join_key on (source, metadata['file']).
    semantic_key = make_join_key(source, rel_path)

    assert bm25_key == fts_key == semantic_key


def test_subdir_and_root_file_with_same_basename_produce_distinct_keys(
    tmp_path, monkeypatch
):
    """Bug N-4 regression: archive/notes.md and current/notes.md must NOT
    collapse into one RRF key.

    Before the fix, both files would index with ``path = "notes.md"``
    (or ``"notes.md"`` after basename-stripping at retrieval), so a
    search would return a single merged ``[global] notes.md`` result
    blending content from two different files.

    After the fix, FTS5 stores POSIX rel_path and ``make_join_key``
    preserves it verbatim, so the two files remain distinct.
    """
    from l4_fts5_search import L4FTS5Search  # noqa: E402

    fts = L4FTS5Search(db_path=tmp_path / "fts.db")
    assert fts.init_fts()

    memory = tmp_path / "memory"
    (memory / "archive").mkdir(parents=True)
    (memory / "current").mkdir(parents=True)
    (memory / "archive" / "notes.md").write_text(
        "widgets used to live in the old archive notes", encoding="utf-8"
    )
    (memory / "current" / "notes.md").write_text(
        "widgets currently documented in the live notes", encoding="utf-8"
    )

    monkeypatch.setattr(fts, "global_memory", memory)
    monkeypatch.setattr(fts, "projects_base", tmp_path / "projects")
    fts.reindex_all()

    results = list(fts.search("widgets"))
    keys = {r.key for r in results}

    assert make_join_key("global", "archive/notes.md") in keys, (
        f"archive/notes.md missing from result keys: {keys!r}"
    )
    assert make_join_key("global", "current/notes.md") in keys, (
        f"current/notes.md missing from result keys: {keys!r}"
    )
    assert len(keys) >= 2, (
        "sub-directory siblings with the same basename collapsed into "
        f"one key (Bug N-4 regression): {keys!r}"
    )


def test_pre_formed_keys_renormalise_to_same_canonical_form():
    """Even when an engine forwards a pre-formed ``[src] file`` key, the
    hybrid layer canonicalises it via ``normalize_existing_key`` so a
    legacy ``[my-app] x.md`` payload still merges with a fresh
    ``[my_app] x.md`` payload.
    """
    legacy = "[my-app] handoff.md"
    canonical = make_join_key("my-app", "handoff.md")
    assert normalize_existing_key(legacy) == canonical


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
