#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the structured health check (scripts/health_check.py)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import health_check  # noqa: E402

REQUIRED_TOP_KEYS = {"version", "fts", "routing", "costs", "system", "status"}
VALID_STATUSES = {"ok", "degraded", "down"}


class _FakeFts:
    def stats(self):
        return {
            "total_documents": 7,
            "db_size_kb": 12.5,
            "db_path": str(Path.home() / ".claude" / "memory_fts5.db"),
            "sources": {"global": 7},
        }


class _FakeLearner:
    def stats(self):
        return {"total_tasks": 0, "routing_phase": "cold_start"}


class _FakeCost:
    def get_stats(self, days=7):
        return {"total_cost": 0.0, "total_operations": 0, "period_days": days}


def _collect(**kwargs):
    defaults = dict(
        fts=_FakeFts(),
        cost_tracker=_FakeCost(),
        routing_learner=_FakeLearner(),
        include_semantic=False,
    )
    defaults.update(kwargs)
    return health_check.collect_health(**defaults)


def test_collect_health_has_required_keys():
    health = _collect()
    assert REQUIRED_TOP_KEYS.issubset(health.keys())
    assert health["status"] in VALID_STATUSES


def test_collect_health_reports_injected_values():
    health = _collect()
    assert health["fts"]["ok"] is True
    assert health["fts"]["total_documents"] == 7
    assert health["routing"]["phase"] == "cold_start"
    assert health["costs"]["spend_7d_usd"] == 0.0


def test_collect_health_fts_failure_is_down():
    class _BoomFts:
        def stats(self):
            raise RuntimeError("db gone")

    health = _collect(fts=_BoomFts())
    assert health["fts"]["ok"] is False
    assert health["status"] == "down"


def test_collect_health_payload_is_json_serializable():
    health = _collect()
    encoded = json.dumps(health, default=str)
    assert "status" in json.loads(encoded)


def test_main_json_mode_exits_zero(capsys):
    fake = {
        "version": "v1.6.0",
        "fts": {"ok": True, "db_exists": True},
        "routing": {"ok": True},
        "costs": {"ok": True},
        "system": {},
        "status": "ok",
    }
    with patch.object(health_check, "collect_health", return_value=fake):
        rc = health_check.main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["status"] == "ok"


def test_main_human_mode_down_exits_nonzero(capsys):
    fake = {
        "version": "v1.6.0",
        "fts": {"ok": False, "error": "boom"},
        "routing": {"ok": True},
        "costs": {"ok": True},
        "system": {},
        "status": "down",
    }
    with patch.object(health_check, "collect_health", return_value=fake):
        rc = health_check.main([])
    captured = capsys.readouterr()
    assert rc == 1
    assert "DOWN" in captured.out


def test_mcp_health_check_tool_wraps_collect_health():
    import mcp_server

    fake = {"status": "ok", "version": "v1.6.0"}
    with patch("health_check.collect_health", return_value=fake):
        result = mcp_server.health_check()
    assert result["success"] is True
    assert result["health"]["status"] == "ok"
