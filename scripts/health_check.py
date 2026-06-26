#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured health/readiness check for the Claude 4-layer memory system.

Aggregates the operational state of every layer -- the FTS5 keyword index, the
semantic ChromaDB backend, the routing learner, and the cost ledger -- together
with a few host facts into a single JSON-serializable payload. It backs both the
``health_check`` MCP tool and the ``cm doctor`` CLI command, and can be run
standalone for CI/local smoke checks::

    python scripts/health_check.py            # human-readable summary
    python scripts/health_check.py --json     # machine-readable payload

Every probe degrades gracefully: a failure in one layer is captured as that
layer's ``error`` string and downgrades the overall ``status`` instead of
raising, so calling this is always safe.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

REPO_ROOT = SCRIPTS_DIR.parent
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SEMANTIC_DB_CANDIDATES = (
    CLAUDE_DIR / "semantic_db_global",
    CLAUDE_DIR / "chroma_db",
)
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_DOWN = "down"


def _read_version() -> str:
    """Return the repository version string, or ``\"unknown\"`` if unreadable."""
    try:
        return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _detect_model_cache(model: str) -> Optional[bool]:
    """Best-effort check for a locally cached Hugging Face model snapshot."""
    try:
        hf_home = os.environ.get("HF_HOME")
        base = Path(hf_home) if hf_home else (HOME / ".cache" / "huggingface")
        hub = base / "hub"
        if not hub.exists():
            return False
        slug = model.split("/")[-1].lower()
        for entry in hub.iterdir():
            if entry.is_dir() and slug in entry.name.lower():
                return True
        return False
    except OSError:
        return None


def _fts_health(fts: Optional[Any]) -> dict[str, Any]:
    """Probe the FTS5 keyword index."""
    try:
        engine = fts
        if engine is None:
            from l4_fts5_search import L4FTS5Search  # pylint: disable=import-error

            engine = L4FTS5Search()
        stats = engine.stats()
        db_path = str(stats.get("db_path") or "")
        return {
            "ok": True,
            "db_path": db_path or None,
            "db_exists": bool(db_path) and Path(db_path).exists(),
            "total_documents": stats.get("total_documents", 0),
            "db_size_kb": stats.get("db_size_kb", 0),
            "sources": stats.get("sources", {}),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _semantic_health() -> dict[str, Any]:
    """Probe the semantic ChromaDB backend without loading the model."""
    db_path = None
    for candidate in SEMANTIC_DB_CANDIDATES:
        if candidate.exists():
            db_path = candidate
            break

    model = os.environ.get("L4_MODEL", DEFAULT_MODEL)
    result: dict[str, Any] = {
        "db_path": str(db_path) if db_path is not None else None,
        "db_exists": db_path is not None,
        "model": model,
        "model_cached": _detect_model_cache(model),
    }

    if db_path is None:
        result["ok"] = True
        result["chroma_reachable"] = False
        result["note"] = "semantic db not initialized"
        return result

    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        collections = {col.name: col.count() for col in client.list_collections()}
        result["ok"] = True
        result["chroma_reachable"] = True
        result["collections"] = collections
        result["total_documents"] = sum(collections.values())
    except ImportError:
        result["ok"] = True
        result["chroma_reachable"] = False
        result["note"] = "chromadb not installed"
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["chroma_reachable"] = False
        result["error"] = str(exc)
    return result


def _routing_health(learner: Optional[Any]) -> dict[str, Any]:
    """Probe the routing learner."""
    try:
        engine = learner
        if engine is None:
            from routing_learner import get_learner  # pylint: disable=import-error

            engine = get_learner()
        stats = engine.stats()
        return {
            "ok": True,
            "history_count": stats.get("total_tasks", 0),
            "phase": stats.get("routing_phase"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _costs_health(tracker: Optional[Any]) -> dict[str, Any]:
    """Probe the cost ledger."""
    try:
        engine = tracker
        if engine is None:
            from cost_tracker import CostTracker  # pylint: disable=import-error

            engine = CostTracker()
        today = engine.get_stats(days=1)
        week = engine.get_stats(days=7)
        return {
            "ok": True,
            "spend_today_usd": round(float(today.get("total_cost") or 0.0), 4),
            "spend_7d_usd": round(float(week.get("total_cost") or 0.0), 4),
            "operations_7d": week.get("total_operations", 0),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _system_health() -> dict[str, Any]:
    """Collect host facts relevant to operating the memory system."""
    info: dict[str, Any] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "claude_dir": str(CLAUDE_DIR),
        "claude_dir_exists": CLAUDE_DIR.exists(),
    }
    try:
        usage = shutil.disk_usage(str(HOME))
        info["free_disk_gb"] = round(usage.free / (1024 ** 3), 2)
    except OSError as exc:
        info["free_disk_gb"] = None
        info["disk_error"] = str(exc)
    return info


def _derive_status(components: dict[str, Any]) -> str:
    """Roll component probes up into ok | degraded | down."""
    fts = components.get("fts", {})
    if not fts.get("ok", False):
        return STATUS_DOWN

    degraded = not fts.get("db_exists", False)
    for layer in ("semantic", "routing", "costs"):
        component = components.get(layer)
        if component is not None and not component.get("ok", True):
            degraded = True
    if degraded:
        return STATUS_DEGRADED
    return STATUS_OK


def collect_health(
    *,
    fts: Optional[Any] = None,
    cost_tracker: Optional[Any] = None,
    routing_learner: Optional[Any] = None,
    include_semantic: bool = True,
) -> dict[str, Any]:
    """Assemble the full structured health payload.

    Args:
        fts: Optional pre-built FTS5 engine to reuse (avoids re-opening the DB).
        cost_tracker: Optional pre-built cost tracker to reuse.
        routing_learner: Optional pre-built routing learner to reuse.
        include_semantic: When ``False``, skip the semantic ChromaDB probe.

    Returns:
        A JSON-serializable dict with ``version``, ``fts``, ``routing``,
        ``costs``, ``system``, an optional ``semantic`` section, and an overall
        ``status`` of ``ok`` | ``degraded`` | ``down``.
    """
    components: dict[str, Any] = {
        "version": _read_version(),
        "fts": _fts_health(fts),
        "routing": _routing_health(routing_learner),
        "costs": _costs_health(cost_tracker),
        "system": _system_health(),
    }
    if include_semantic:
        components["semantic"] = _semantic_health()
    components["status"] = _derive_status(components)
    return components


def _print_human(health: dict[str, Any]) -> None:
    """Print a compact human-readable health summary to stdout."""
    status = str(health.get("status", "unknown")).upper()
    print(f"[DOCTOR] claude-4layer-memory  status={status}")
    print(f"  version           : {health.get('version')}")

    fts = health.get("fts", {})
    if fts.get("ok"):
        line = (
            f"  fts5 index        : ok (docs={fts.get('total_documents')}, "
            f"size_kb={fts.get('db_size_kb')}, exists={fts.get('db_exists')})"
        )
    else:
        line = f"  fts5 index        : FAIL ({fts.get('error')})"
    print(line)

    semantic = health.get("semantic")
    if semantic is not None:
        if semantic.get("ok"):
            line = (
                f"  semantic backend  : ok (reachable={semantic.get('chroma_reachable')}, "
                f"model_cached={semantic.get('model_cached')})"
            )
        else:
            line = f"  semantic backend  : FAIL ({semantic.get('error')})"
        print(line)

    routing = health.get("routing", {})
    if routing.get("ok"):
        line = (
            f"  routing learner   : ok (history={routing.get('history_count')}, "
            f"phase={routing.get('phase')})"
        )
    else:
        line = f"  routing learner   : FAIL ({routing.get('error')})"
    print(line)

    costs = health.get("costs", {})
    if costs.get("ok"):
        line = (
            f"  cost ledger       : ok (today=${costs.get('spend_today_usd')}, "
            f"7d=${costs.get('spend_7d_usd')})"
        )
    else:
        line = f"  cost ledger       : FAIL ({costs.get('error')})"
    print(line)

    system = health.get("system", {})
    print(
        f"  system            : python={system.get('python_version')}, "
        f"free_disk_gb={system.get('free_disk_gb')}"
    )


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for ``python scripts/health_check.py``."""
    parser = argparse.ArgumentParser(
        description="Health/readiness check for the Claude 4-layer memory system.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the raw JSON payload instead of a human summary",
    )
    parser.add_argument(
        "--no-semantic",
        dest="semantic",
        action="store_false",
        help="skip the semantic ChromaDB probe",
    )
    args = parser.parse_args(argv)

    health = collect_health(include_semantic=args.semantic)

    if args.json:
        print(json.dumps(health, indent=2, ensure_ascii=False, default=str))
        return 0

    _print_human(health)
    return 1 if health.get("status") == STATUS_DOWN else 0


if __name__ == "__main__":
    sys.exit(main())
