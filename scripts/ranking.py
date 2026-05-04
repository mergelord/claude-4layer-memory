#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reciprocal Rank Fusion (RRF) ranking for hybrid memory search.

Combines two or more independent ranking streams (e.g. FTS5 BM25 and
ChromaDB cosine similarity) into a single explainable ranking. The
output preserves per-source metadata so callers can answer the question
"why was this result selected, and which engine contributed?".

The merge is deterministic: ties on RRF score are broken by the join
key (lexicographic). Multiple hits from the same source for the same
key (e.g. two FTS chunks of the same file) are *both* recorded under
that source — they are not silently overwritten.

Public API
----------
- :class:`RankedResult` — frozen dataclass returned to consumers.
- :func:`rrf_merge` — variadic merge over named streams.
- :func:`normalize_scores` — adds ``normalized_score`` field in [0, 1].

References
----------
Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and
Individual Rank Learning Methods", SIGIR 2009.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Tuple

DEFAULT_K = 60
"""Standard RRF damping constant (Cormack 2009)."""


@dataclass
class RankedResult:
    """A single merged ranking entry with source-attribution.

    Attributes:
        key: Stable identifier used to join across sources (typically
            a normalised file path or ``"[scope] filename"`` string).
        score: Sum of per-source RRF contributions ``1 / (k + rank)``.
        normalized_score: Score divided by the max score in the result
            set. Set by :func:`normalize_scores`. Range ``[0.0, 1.0]``.
        sources: Mapping of source-name → list of per-hit explanations.
            Stored as a list (not dict) so multiple chunks from the
            same source for the same key are preserved.
    """

    key: str
    score: float = 0.0
    normalized_score: float = 0.0
    sources: dict[str, List[dict[str, Any]]] = field(default_factory=dict)


def rrf_merge(
    *streams: Tuple[str, Iterable[Mapping[str, Any]]],
    k: int = DEFAULT_K,
) -> List[RankedResult]:
    """Merge two or more ranking streams via Reciprocal Rank Fusion.

    Args:
        *streams: Variadic ``(source_name, items)`` pairs. Each item
            must be a :class:`Mapping` containing at least a ``"key"``
            field used to identify the document across streams. All
            other fields are preserved verbatim under the per-source
            explanation list — they are opaque to the merger.
        k: RRF damping constant. Higher values flatten the ranking;
            lower values emphasise top results. Default 60 follows
            Cormack 2009.

    Returns:
        List of :class:`RankedResult` ordered by descending score.
        Ties on score are broken deterministically by ``key`` so that
        the same input always produces the same output.

    Raises:
        ValueError: If ``k`` is negative or any item lacks a ``"key"``.

    Examples:
        >>> fts = [{"key": "a.md", "rank": 0.9}, {"key": "b.md", "rank": 0.5}]
        >>> sem = [{"key": "a.md", "distance": 0.1}, {"key": "c.md", "distance": 0.4}]
        >>> merged = rrf_merge(("fts", fts), ("semantic", sem))
        >>> [r.key for r in merged]
        ['a.md', 'b.md', 'c.md']
    """
    if k < 0:
        raise ValueError(f"rrf k must be non-negative, got {k}")

    accumulator: dict[str, RankedResult] = {}

    for source_name, items in streams:
        # ``enumerate`` from 1 because RRF rank is 1-based.
        for rank, item in enumerate(items, start=1):
            if "key" not in item:
                raise ValueError(
                    f"stream {source_name!r}: item at rank {rank} is "
                    f"missing required 'key' field: {item!r}"
                )
            key = str(item["key"])
            contribution = 1.0 / (k + rank)

            entry = accumulator.setdefault(key, RankedResult(key=key))
            entry.score += contribution

            # Strip 'key' from the per-source payload so it's not
            # duplicated, but keep everything else for explainability.
            payload = {field_: value for field_, value in item.items() if field_ != "key"}
            payload["rank"] = rank
            payload["rrf_contribution"] = contribution

            entry.sources.setdefault(source_name, []).append(payload)

    # Stable tie-break: descending score, then ascending key.
    return sorted(accumulator.values(), key=lambda r: (-r.score, r.key))


def normalize_scores(results: List[RankedResult]) -> List[RankedResult]:
    """Set ``normalized_score`` on every result in-place and return it.

    Normalises against the maximum score in ``results`` so the top hit
    always reports ``normalized_score == 1.0``. This is a UI/UX signal,
    *not* a probability — RRF scores are not probabilities.

    Edge case: if ``results`` is empty or every score is ``0.0`` (which
    can happen with very large ``k`` and few sources), every result is
    assigned ``0.0`` rather than triggering a division-by-zero.

    Args:
        results: Output of :func:`rrf_merge`. Mutated in place.

    Returns:
        The same list, returned for chaining.
    """
    if not results:
        return results

    max_score = max(r.score for r in results)
    if max_score <= 0:
        for r in results:
            r.normalized_score = 0.0
        return results

    for r in results:
        r.normalized_score = r.score / max_score
    return results
