"""Calibration tests for the RRF damping constant ``k=60``.

These tests fix the expected behaviour of :func:`scripts.ranking.rrf_merge`
in three scenarios identified during architectural review as critical
for explainable hybrid search:

1. **Obvious case** - one document dominates both sources; it must be
   top of the merged ranking.
2. **Single-source dominance / FTS-vs-semantic conflict** - when each
   source has a different top hit (e.g. keyword-only vs meaning-only
   match), neither wins outright; RRF reports them as tied and the
   merger breaks the tie deterministically by key.
3. **Many-weak-vs-one-strong** - documents appearing in *both* sources
   at middle ranks beat a document that appears in only one source at
   rank 1. This is RRF's defining property: consensus across sources
   is rewarded over single-source dominance.

The third case also documents the trade-off in choosing ``k``: a low
``k`` flips the result and lets a single rank-1 hit dominate; the
default ``k=60`` (Cormack 2009) was chosen because the consensus
property is the entire purpose of merging.

If a future change to the merger logic or to ``DEFAULT_K`` alters the
ordering in any of these cases, this file will fail loudly and link
the maintainer back to this rationale.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# pylint: disable=wrong-import-position
from ranking import DEFAULT_K, rrf_merge  # noqa: E402


# ---------------------------------------------------------------------------
# Case 1: obvious match - same document dominates both sources
# ---------------------------------------------------------------------------


def test_obvious_case_top_match_in_both_sources_wins():
    """Document ``A.md`` is rank 1 in both FTS and semantic; nothing
    else appears at the top in both. Expected: ``A.md`` is the top RRF
    result.

    This is the trivial sanity case - if RRF couldn't surface this,
    the whole exercise would be pointless.
    """
    fts = [
        {"key": "A.md"},   # rank 1
        {"key": "B.md"},   # rank 2
        {"key": "C.md"},   # rank 3
        {"key": "D.md"},   # rank 4
    ]
    sem = [
        {"key": "A.md"},   # rank 1
        {"key": "C.md"},   # rank 2
        {"key": "B.md"},   # rank 3
        {"key": "D.md"},   # rank 4
    ]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    assert merged[0].key == "A.md", (
        f"obvious top match must win; got order {[r.key for r in merged]}"
    )
    # Spot-check: A should appear in both sources' attribution.
    assert set(merged[0].sources.keys()) == {"fts", "semantic"}


# ---------------------------------------------------------------------------
# Case 2: single-source dominance - keyword-only vs semantic-only top hit
# ---------------------------------------------------------------------------


def test_conflict_single_source_top_hits_tie_and_break_by_key():
    """File A is rank 1 in FTS only (e.g. exact keyword match that is
    semantically off-topic). File B is rank 1 in semantic only (e.g.
    paraphrase with no token overlap). Both have identical RRF scores
    (one ``1/(k+1)`` contribution each). The merger breaks the tie by
    ascending key for determinism.

    This documents an important limit of RRF: a single source cannot
    out-rank another single source at the same rank. If you want
    keyword matches to dominate semantic matches (or vice versa), you
    need source weights, not just RRF.
    """
    fts = [{"key": "A_keyword_only.md"}]
    sem = [{"key": "B_semantic_only.md"}]

    merged = rrf_merge(("fts", fts), ("semantic", sem))

    expected_score = 1.0 / (DEFAULT_K + 1)
    assert len(merged) == 2
    assert merged[0].score == expected_score
    assert merged[1].score == expected_score
    assert merged[0].score == merged[1].score
    # Lexicographic tie-break: A < B.
    assert merged[0].key == "A_keyword_only.md"
    assert merged[1].key == "B_semantic_only.md"


# ---------------------------------------------------------------------------
# Case 3: many-weak-vs-one-strong (the consensus property)
# ---------------------------------------------------------------------------


def test_many_weak_cross_source_signals_beat_one_strong_single_source():
    """At ``k=60``, two documents (Y, Z) that appear at middle ranks in
    *both* sources outrank a document (X) that appears at rank 1 in
    one source only.

    Numerical sanity (``k=60``):

    - X score = ``1/(60+1)`` ≈ ``0.01639``
    - Y score = ``1/(60+4) + 1/(60+3)`` ≈ ``0.01563 + 0.01587`` ≈ ``0.03150``
    - Z score = ``1/(60+5) + 1/(60+4)`` ≈ ``0.01538 + 0.01563`` ≈ ``0.03101``

    Both Y and Z roughly double X's score. This is the entire point of
    hybrid search: cross-source consensus is more informative than
    single-source dominance.
    """
    fts = [
        {"key": "X.md"},   # rank 1, FTS only
        {"key": "P.md"},   # rank 2, filler
        {"key": "Q.md"},   # rank 3, filler
        {"key": "Y.md"},   # rank 4, also in semantic
        {"key": "Z.md"},   # rank 5, also in semantic
    ]
    sem = [
        {"key": "P.md"},   # rank 1, filler
        {"key": "Q.md"},   # rank 2, filler
        {"key": "Y.md"},   # rank 3
        {"key": "Z.md"},   # rank 4
    ]

    merged = rrf_merge(("fts", fts), ("semantic", sem), k=60)
    keys = [r.key for r in merged]

    assert keys.index("Y.md") < keys.index("X.md"), (
        f"Y (rank 4 FTS + rank 3 semantic) must beat X (rank 1 FTS only); "
        f"got order {keys}"
    )
    assert keys.index("Z.md") < keys.index("X.md"), (
        f"Z (rank 5 FTS + rank 4 semantic) must beat X (rank 1 FTS only); "
        f"got order {keys}"
    )


# ---------------------------------------------------------------------------
# Counter-case: low k inverts the trade-off (documents the choice)
# ---------------------------------------------------------------------------


def test_low_k_inverts_consensus_rewards_single_source_dominance():
    """At ``k=0`` the same setup as case 3 produces the opposite order:
    X (rank 1 in one source) outranks Y/Z (rank 3-5 in both).

    Why this matters:

    - ``k`` controls how aggressively top ranks are emphasised.
    - At ``k=0``, ``1/(0+1)`` = 1.0 and ``1/(0+4)`` = 0.25 — the
      damping is so steep that a single rank-1 always wins.
    - At ``k=60`` (default), the curve is flat enough that two
      mid-rank hits sum past one rank-1 hit.

    Locking ``DEFAULT_K=60`` is therefore not arbitrary: it is the
    point at which RRF starts behaving like a *consensus* operator
    rather than a max-of-top-ranks operator. Lower the constant and
    you collapse RRF back into something close to a winner-takes-all
    union; raise it dramatically and ranks become indistinguishable.
    """
    fts = [
        {"key": "X.md"},
        {"key": "P.md"},
        {"key": "Q.md"},
        {"key": "Y.md"},
        {"key": "Z.md"},
    ]
    sem = [
        {"key": "P.md"},
        {"key": "Q.md"},
        {"key": "Y.md"},
        {"key": "Z.md"},
    ]

    merged = rrf_merge(("fts", fts), ("semantic", sem), k=0)
    keys = [r.key for r in merged]

    assert keys.index("X.md") < keys.index("Y.md")
    assert keys.index("X.md") < keys.index("Z.md")


# ---------------------------------------------------------------------------
# Default-k pin: catches accidental DEFAULT_K bumps
# ---------------------------------------------------------------------------


def test_default_k_is_pinned_to_60():
    """Pin the default to 60 (Cormack 2009).

    This isn't an architectural law, but the calibration cases above
    were chosen *because* of the behaviour at ``k=60``. If we ever
    change the default we must re-run those cases against real memory
    data and reconfirm the consensus-vs-dominance trade-off is still
    the one we want.
    """
    assert DEFAULT_K == 60, (
        "DEFAULT_K changed; re-validate the three calibration cases in "
        "this file against real memory before merging."
    )
