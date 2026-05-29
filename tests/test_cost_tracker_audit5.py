#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT #5 regression tests for CostTracker._load_prices exception narrowing.

The price-config loader was narrowed from a blanket ``except Exception`` to
``(OSError, json.JSONDecodeError, UnicodeDecodeError)``. These tests pin both
directions of that contract:
  - expected config-load failures (malformed JSON) degrade to DEFAULT_PRICES;
  - a valid config file is actually parsed and used (the try path returns it);
  - an unexpected error inside the loader propagates instead of being masked
    as a silent fallback to defaults.

All tests stay inside tmp_path; the real ~/.claude config is never touched.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cost_tracker as cost_tracker_mod  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402


def _point_config_at(tmp_path, monkeypatch, contents):
    """Redirect _load_prices to a temp ``config/prices.json``.

    _load_prices reads ``Path(__file__).parent.parent / 'config' /
    'prices.json'``; faking the module ``__file__`` to
    ``tmp_path/scripts/cost_tracker.py`` makes it resolve to
    ``tmp_path/config/prices.json``. Mirrors the layout trick already used in
    test_cost_tracker.py::test_load_prices_from_file.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    if contents is not None:
        (config_dir / "prices.json").write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        cost_tracker_mod, "__file__", str(scripts_dir / "cost_tracker.py")
    )


def test_load_prices_malformed_json_falls_back_to_defaults(
    tmp_path, monkeypatch, capsys
):
    _point_config_at(tmp_path, monkeypatch, "{ not valid json ")
    tracker = CostTracker(db_path=tmp_path / "costs.db")
    assert tracker.prices == CostTracker.DEFAULT_PRICES
    err = capsys.readouterr().err
    assert "Failed to load prices.json" in err
    assert "Using default prices" in err


def test_load_prices_valid_file_is_parsed_and_used(tmp_path, monkeypatch):
    _point_config_at(
        tmp_path,
        monkeypatch,
        '{"claude-sonnet-4": {"input": 7.0, "output": 9.0}}',
    )
    tracker = CostTracker(db_path=tmp_path / "costs.db")
    assert tracker.prices["claude-sonnet-4"]["input"] == 7.0


def test_load_prices_unexpected_error_propagates(tmp_path, monkeypatch):
    _point_config_at(
        tmp_path,
        monkeypatch,
        '{"claude-sonnet-4": {"input": 1.0, "output": 2.0}}',
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("unexpected prices failure")

    # RuntimeError is NOT in the narrowed
    # (OSError, json.JSONDecodeError, UnicodeDecodeError) tuple, so it must
    # propagate rather than silently falling back to DEFAULT_PRICES.
    monkeypatch.setattr(cost_tracker_mod.json, "load", boom)
    with pytest.raises(RuntimeError, match="unexpected prices failure"):
        CostTracker(db_path=tmp_path / "costs.db")
