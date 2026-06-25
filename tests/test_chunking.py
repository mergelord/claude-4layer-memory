#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for scripts/chunking.py — paragraph chunking and overlap behavior."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from chunking import chunk_text  # noqa: E402


def test_basic_chunking_returns_single_chunk():
    """Short text below the limit yields exactly one chunk."""
    assert chunk_text("hello world") == ["hello world"]


def test_empty_input_returns_empty_list():
    """Empty or whitespace-only input yields no chunks."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_overlap_prepended_in_normal_case():
    """When overlap fits, the last paragraph carries into the next chunk."""
    a = "a" * 8
    b = "b" * 8
    c = "c" * 8
    text = f"{a}\n\n{b}\n\n{c}"
    chunks = chunk_text(text, max_chars=20, overlap_paragraphs=1)
    # First chunk holds a+b; the boundary carries b into the next chunk.
    assert chunks[0] == f"{a}\n\n{b}"
    assert chunks[1].startswith(b)
    assert c in chunks[1]


def test_overflow_boundary_no_duplicate_overlap_chunk():
    """When carry_over + para exceeds max_chars, overlap is dropped cleanly.

    Regression test for the P3 overlap fix: the overlap paragraph must NOT be
    re-emitted as a standalone duplicate chunk (it is already contained in the
    previous chunk).
    """
    a = "a" * 12
    b = "b" * 12
    text = f"{a}\n\n{b}"
    chunks = chunk_text(text, max_chars=20, overlap_paragraphs=1)
    assert chunks == [a, b]
    # No chunk should be a pure duplicate of another.
    assert len(chunks) == len(set(chunks))


def test_no_empty_chunks():
    """Chunker never returns empty or whitespace-only chunks."""
    text = "para one\n\n\n\npara two\n\n   \n\npara three"
    chunks = chunk_text(text, max_chars=20, overlap_paragraphs=1)
    assert all(c.strip() for c in chunks)
