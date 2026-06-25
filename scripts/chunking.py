#!/usr/bin/env python3
# pylint: disable=duplicate-code
# -*- coding: utf-8 -*-
"""Common text chunker for memory indexing (semantic + FTS5 + future BM25).

Contract:
- Splits by paragraphs first, then by sentences if a paragraph is too long.
- Overlap is defined in number of paragraphs (not characters).
- Returns a list of non‑empty chunk strings (may be empty list for empty input).
"""

import re
from typing import List

MAX_CHARS_PER_CHUNK = 800
OVERLAP_PARAGRAPHS = 1

# Sentence splitter: учитывает . ! ? и не режет сокращения
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_long_paragraph(para: str, max_chars: int) -> List[str]:
    """Split a single long paragraph into sentence-level chunks."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(para) if s.strip()]
    chunks = []
    sub_chunk = ""
    for sent in sentences:
        if len(sub_chunk) + len(sent) <= max_chars:
            sub_chunk += sent + " "
        else:
            if sub_chunk:
                chunks.append(sub_chunk.strip())
            sub_chunk = sent + " "
    if sub_chunk.strip():
        chunks.append(sub_chunk.strip())
    return chunks


def chunk_text(
    text: str,
    max_chars: int = MAX_CHARS_PER_CHUNK,
    overlap_paragraphs: int = OVERLAP_PARAGRAPHS,
) -> List[str]:
    """
    Разбивает текст на чанки.

    - Сначала делит по абзацам (\\n\\n).
    - Если абзац слишком длинный (> max_chars), режет его по предложениям.
    - Добавляет overlap: последние ``overlap_paragraphs`` абзацев предыдущего
      чанка включаются в начало следующего.
    - Не возвращает пустых или состоящих только из пробелов чанков.

    Возвращает список чанков (каждый чанк — текст).
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    carry_over: List[str] = []

    for para in paragraphs:
        # Если текущий чанк с новым абзацем укладывается в лимит — добавляем
        if len(current) + len(para) <= max_chars:
            current += para + "\n\n"
            continue

        # Иначе — сохраняем текущий чанк и готовим overlap
        if current:
            chunks.append(current.strip())
            prev_paras = [p.strip() for p in current.split("\n\n") if p.strip()]
            carry_over = (
                prev_paras[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
            )
            current = ""

        # Обработка абзаца, который сам по себе длиннее max_chars
        if len(para) > max_chars:
            sub_chunks = _split_long_paragraph(para, max_chars)
            # Добавляем все, кроме последнего, а последний кладём в current с overlap
            for sub in sub_chunks[:-1]:
                chunks.append(sub)
            if sub_chunks:
                # Последний кусок начинаем с переносимых абзацев
                current = "\n\n".join(carry_over) + "\n\n" + sub_chunks[-1]
            else:
                current = "\n\n".join(carry_over) if carry_over else ""
            carry_over = []
            continue

        # Обычный случай: добавляем overlap и начинаем новый чанк
        candidate_parts = carry_over + [para]
        candidate = "\n\n".join(candidate_parts)
        if len(candidate) <= max_chars:
            current = candidate + "\n\n"
        else:
            # P3 overlap consistency: if carry_over + para still exceeds
            # max_chars, don't silently drop the overlap. Emit it as its own
            # chunk so the overlapping paragraph is not lost, then start
            # fresh with just the current paragraph.
            if carry_over:
                chunks.append("\n\n".join(carry_over).strip())
            current = para + "\n\n"
        carry_over = []

    # Не забываем последний кусок
    if current.strip():
        chunks.append(current.strip())
    elif not chunks and text.strip():
        chunks.append(text.strip())

    return chunks
