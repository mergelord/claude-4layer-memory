#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the additive L4Config.logs_dir path property."""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_config  # noqa: E402


def test_logs_dir_defaults_to_home_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("L4_HOME", str(tmp_path))
    cfg = l4_config.get_config()
    assert cfg.logs_dir == tmp_path / "logs"


def test_logs_dir_is_under_home(tmp_path):
    cfg = l4_config.get_config(home=tmp_path)
    assert cfg.logs_dir.parent == cfg.home
    assert cfg.logs_dir.name == "logs"
