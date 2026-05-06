#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common text chunker for memory indexing (semantic + FTS5 + future BM25).

Contract:
- Splits by paragraphs first, then by sentences if a paragraph is too long.
- Overlap is defined in number of paragraphs (not characters).
- Returns a list of chunk strings.
"""

from typing import List

MAX_CHARS_PER_CHUNK = 800
OVERLAP_PARAGRAPHS = 1


def _split_long_paragraph(para: str, max_chars: int) -> List[str]:
    """Split a single long paragraph into sentence-level chunks."""
    sentences = [s.strip() for s in para.replace('\n', ' ').split('.') if s.strip()]
    chunks = []
    sub_chunk = ""
    for sent in sentences:
        if len(sub_chunk) + len(sent) <= max_chars:
            sub_chunk += sent + '. '
        else:
            if sub_chunk:
                chunks.append(sub_chunk.strip())
            sub_chunk = sent + '. '
    if sub_chunk:
        chunks.append(sub_chunk.strip())
    return chunks


def chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK,
               overlap_paragraphs: int = OVERLAP_PARAGRAPHS) -> List[str]:
    """
    Разбивает текст на чанки.

    - Сначала делит по абзацам (\\n\\n).
    - Если абзац слишком длинный (> max_chars), режет его по предложениям.
    - Добавляет overlap: последние ``overlap_paragraphs`` абзацев предыдущего
      чанка включаются в начало следующего.

    Возвращает список чанков (каждый чанк — текст).
    """
    paragraphs = text.split('\n\n')
    chunks = []
    current = ""
    carry_over: List[str] = []

    for para in paragraphs:
        if len(current) + len(para) <= max_chars:
            current += para + '\n\n'
        else:
            if current:
                chunks.append(current.strip())
                prev_paras = [p.strip() for p in current.split('\n\n') if p.strip()]
                carry_over = prev_paras[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
                current = ""
            if len(para) > max_chars:
                sub_chunks = _split_long_paragraph(para, max_chars)
                if sub_chunks:
                    current = sub_chunks.pop()  # последний короткий может быть начат
                    chunks.extend(sub_chunks)
            else:
                current = '\n\n'.join(carry_over) + '\n\n' + para + '\n\n'
                carry_over = []

    if current.strip():
        chunks.append(current.strip())
    elif not chunks:
        chunks.append(text.strip())
    return chunks