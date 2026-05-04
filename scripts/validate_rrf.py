#!/usr/bin/env python3
"""Human-readable inspector for RRF behaviour on synthetic or real data.

This is *not* an automated test. It's a CLI for humans who want to
eyeball how the merger orders documents under different ``k`` values
or with custom rank lists. The automated equivalents live in
``tests/test_rrf_calibration.py`` and lock the three canonical cases
(obvious / single-source-dominance / many-weak-vs-one-strong) into CI.

Usage
-----

Run the three canonical scenarios at the default ``k=60``::

    python scripts/validate_rrf.py

Override ``k`` to see how damping affects the ordering::

    python scripts/validate_rrf.py --k 0
    python scripts/validate_rrf.py --k 30

Inspect a specific scenario only::

    python scripts/validate_rrf.py --scenario many_weak_vs_one_strong

Pipe in custom rank lists from JSON for ad-hoc analysis on real data::

    echo '{
        "fts":      [{"key": "a"}, {"key": "b"}],
        "semantic": [{"key": "b"}, {"key": "c"}]
    }' | python scripts/validate_rrf.py --stdin

Output
------

Each scenario prints:

1. Header describing the scenario and the chosen ``k``.
2. The two input rank lists, side by side.
3. The merged ranking with ``score``, ``normalized_score``, and which
   sources contributed to each entry.
4. A short interpretation that names the property being demonstrated.

This script is intentionally dependency-free — only stdlib + the local
``ranking`` module — so it can be dropped into any environment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# pylint: disable-next=wrong-import-position,import-error
from ranking import DEFAULT_K, normalize_scores, rrf_merge  # noqa: E402


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "obvious": {
        "title": "Case 1 - Obvious match",
        "summary": (
            "A.md is rank 1 in both FTS and semantic. The merger should "
            "surface it at the top with both sources contributing."
        ),
        "fts": [{"key": "A.md"}, {"key": "B.md"}, {"key": "C.md"}, {"key": "D.md"}],
        "semantic": [{"key": "A.md"}, {"key": "C.md"}, {"key": "B.md"}, {"key": "D.md"}],
        "expectation": (
            "Top RRF entry: A.md, with sources={fts, semantic}. "
            "This is the trivial sanity case."
        ),
    },
    "fts_vs_semantic_conflict": {
        "title": "Case 2 - Single-source dominance",
        "summary": (
            "A is rank 1 in FTS only (e.g. exact keyword, off-topic). "
            "B is rank 1 in semantic only (e.g. paraphrase, no token "
            "overlap). RRF treats these as a tie and breaks "
            "deterministically by key."
        ),
        "fts": [{"key": "A_keyword_only.md"}],
        "semantic": [{"key": "B_semantic_only.md"}],
        "expectation": (
            "Both rows have identical RRF scores. Order is set by "
            "ascending key. To prefer keyword or semantic, you'd need "
            "source weights, not just RRF."
        ),
    },
    "many_weak_vs_one_strong": {
        "title": "Case 3 - Many weak signals beat one strong signal",
        "summary": (
            "X is rank 1 in FTS only. Y and Z are rank 4-5 in FTS but "
            "ALSO rank 3-4 in semantic. At k=60 the cross-source "
            "consensus signal of Y/Z exceeds the single-source rank-1 "
            "of X. This is RRF's defining property."
        ),
        "fts": [
            {"key": "X.md"},
            {"key": "P.md"},
            {"key": "Q.md"},
            {"key": "Y.md"},
            {"key": "Z.md"},
        ],
        "semantic": [
            {"key": "P.md"},
            {"key": "Q.md"},
            {"key": "Y.md"},
            {"key": "Z.md"},
        ],
        "expectation": (
            "At k=60: Y and Z must rank above X. At k=0 the same "
            "setup produces the opposite order - that demonstrates "
            "WHY 60 is the chosen default."
        ),
    },
}


def _format_rank_list(label: str, items: List[Dict[str, Any]]) -> str:
    """Render a single source's rank list as an aligned column."""
    lines = [f"  {label}:"]
    for rank, item in enumerate(items, start=1):
        lines.append(f"    {rank:>2}. {item['key']}")
    if not items:
        lines.append("    (empty)")
    return "\n".join(lines)


def _format_merged(merged: List[Any]) -> str:
    """Render the merged RRF result with score, normalised score, and sources."""
    if not merged:
        return "  (no merged results)"

    rows = ["  RRF merged ranking:"]
    rows.append(
        f"    {'#':>2}  {'key':<30}  {'score':>8}  {'norm':>5}  sources"
    )
    rows.append(f"    {'-' * 2}  {'-' * 30}  {'-' * 8}  {'-' * 5}  {'-' * 18}")
    for i, entry in enumerate(merged, start=1):
        sources = "+".join(sorted(entry.sources.keys())) or "(none)"
        rows.append(
            f"    {i:>2}  {entry.key:<30}  "
            f"{entry.score:>8.5f}  {entry.normalized_score:>5.3f}  {sources}"
        )
    return "\n".join(rows)


def _run_scenario(name: str, scenario: Dict[str, Any], k: int) -> None:
    """Print one scenario's full report to stdout."""
    print(f"\n{'=' * 72}")
    print(f"{scenario['title']}  (k={k})")
    print("=" * 72)
    print(scenario["summary"])
    print()
    print(_format_rank_list("FTS rank list", scenario["fts"]))
    print()
    print(_format_rank_list("Semantic rank list", scenario["semantic"]))

    merged = normalize_scores(
        rrf_merge(("fts", scenario["fts"]), ("semantic", scenario["semantic"]), k=k)
    )

    print()
    print(_format_merged(merged))
    print()
    print(f"  Expected: {scenario['expectation']}")
    print(f"  Scenario id: {name}")


def _run_stdin_payload(k: int) -> int:
    """Read a custom ``{fts: [...], semantic: [...]}`` JSON blob from stdin.

    Returns ``0`` on a successfully formatted report, ``2`` on any
    input validation failure (mirrors :func:`main`'s contract so a
    programmatic caller invoking ``main(["--stdin"])`` with bad input
    receives a return code rather than an uncaught :class:`SystemExit`).
    """
    raw = sys.stdin.read().strip()
    if not raw:
        print("error: --stdin requires a JSON payload on standard input", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2

    fts = payload.get("fts", [])
    semantic = payload.get("semantic", [])
    if not isinstance(fts, list) or not isinstance(semantic, list):
        print(
            "error: payload must have list-typed 'fts' and 'semantic' fields",
            file=sys.stderr,
        )
        return 2

    print(f"\n{'=' * 72}")
    print(f"Custom payload from stdin  (k={k})")
    print("=" * 72)
    print(_format_rank_list("FTS rank list", fts))
    print()
    print(_format_rank_list("Semantic rank list", semantic))

    merged = normalize_scores(
        rrf_merge(("fts", fts), ("semantic", semantic), k=k)
    )

    print()
    print(_format_merged(merged))
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect RRF behaviour on synthetic scenarios or custom data. "
            "Prints rank lists and merged ranking side by side. Use this "
            "for human inspection; the automated checks live in "
            "tests/test_rrf_calibration.py."
        )
    )
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help=f"RRF damping constant (default: {DEFAULT_K}, Cormack 2009)",
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default=None,
        help="Run a single named scenario instead of all three.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help=(
            "Read a custom payload from standard input as JSON: "
            '{"fts": [{"key": "..."}, ...], "semantic": [{"key": "..."}, ...]}'
        ),
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = _build_argparser()
    args = parser.parse_args(argv)

    if args.k < 0:
        print("error: --k must be non-negative", file=sys.stderr)
        return 2

    if args.stdin:
        return _run_stdin_payload(args.k)

    scenarios_to_run = (
        [(args.scenario, SCENARIOS[args.scenario])]
        if args.scenario
        else list(SCENARIOS.items())
    )

    for name, scenario in scenarios_to_run:
        _run_scenario(name, scenario, args.k)

    return 0


if __name__ == "__main__":
    sys.exit(main())
