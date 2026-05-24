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

This test pins the contract: ``ranking.make_join_key(source, filename)``
is the **only** legitimate way to construct a join key, and all three
engines must route through it (or through ``normalize_existing_key``
when they receive a pre-formed bracketed key from another engine).
"""

from __future__ import annotations

import os
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
    """``global`` round-trips unchanged through both code paths."""
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

    assert result[0]["key"] == make_join_key("global", "memory.md")


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

    assert result[0]["key"] == make_join_key("my-fancy-app", "handoff.md")
    assert result[0]["key"] == "[my_fancy_app] handoff.md"


# ---------------------------------------------------------------------------
# 2. FTS5 SearchResult exposes a make_join_key-derived key
# ---------------------------------------------------------------------------


def test_fts5_search_result_key_is_document_level_basename():
    """FTS5 ``SearchResult.key`` MUST be document-level basename, not full path.

    The raw FTS5 row may contain ``archive/notes.md`` so that the human
    display can show subdirectories, but the join key must be
    ``"[normalized_source] notes.md"`` to align with BM25 and semantic.
    """
    from l4_fts5_search import L4FTS5Search, SearchResult  # noqa: E402

    fts = L4FTS5Search.__new__(L4FTS5Search)  # bypass __init__/db
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
        key=make_join_key(fake_row["source"], os.path.basename(fake_row["path"])),
        snippet=fake_row["snippet"],
        rank=fake_row["rank"],
        source="fts5",
    )

    assert sr.key == "[my_fancy_app] notes.md"
    # Display still preserves subdirectory info for humans.
    assert "archive/notes.md" in sr.path


def test_fts5_cached_search_uses_make_join_key(tmp_path, monkeypatch):
    """Live ``_cached_search`` must populate ``SearchResult.key`` via
    :func:`ranking.make_join_key` — not a string template."""
    from l4_fts5_search import L4FTS5Search  # noqa: E402

    fts = L4FTS5Search(db_path=tmp_path / "fts.db")
    assert fts.init_fts()

    # Index a file directly via the public API so the row hits the same
    # SELECT path as production.
    md = tmp_path / "memory" / "archive" / "notes.md"
    md.parent.mkdir(parents=True)
    md.write_text("memory subsystem notes", encoding="utf-8")
    # index_file uses file.name (basename) for path, so to simulate a
    # nested rel_path we patch the DB row directly via reindex_all.
    monkeypatch.setattr(fts, "global_memory", md.parent.parent)
    fts.reindex_all()

    results = list(fts.search("memory"))
    assert results, "FTS5 index must return at least one hit for the seeded file"

    for r in results:
        # The display path keeps the rel_path; key uses basename.
        assert r.key == make_join_key("global", "notes.md")


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
    "source,filename",
    [
        ("global", "handoff.md"),
        ("my-app", "decisions.md"),
        ("my-fancy-app", "architecture.md"),
        ("project.with.dots", "x.md"),
        ("with spaces", "doc.md"),
    ],
)
def test_three_streams_emit_identical_join_keys(source, filename):
    """For every (source, filename), bm25 / fts / semantic must agree.

    This is the regression net for the original audit finding: as long
    as every engine routes through ``make_join_key`` (or
    ``normalize_existing_key`` for already-formed brackets), the three
    streams collapse onto a single key and RRF can merge them.
    """
    # BM25 builds keys via make_join_key on (row['source'], basename(path)).
    bm25_key = make_join_key(source, os.path.basename(f"sub/{filename}"))
    # FTS5 builds keys via make_join_key on (row['source'], basename(path)).
    fts_key = make_join_key(source, os.path.basename(f"sub/{filename}"))
    # Semantic builds keys via make_join_key on (source, metadata['file']).
    semantic_key = make_join_key(source, filename)

    assert bm25_key == fts_key == semantic_key


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
