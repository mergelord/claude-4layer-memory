#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the centralized L4 configuration module."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import l4_config  # noqa: E402


def test_default_home_is_dot_claude(monkeypatch):
    monkeypatch.delenv("L4_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/fake/user")))
    cfg = l4_config.get_config()
    assert cfg.home == Path("/fake/user") / ".claude"
    assert cfg.memory_dir == Path("/fake/user") / ".claude" / "memory"
    assert cfg.projects_dir == Path("/fake/user") / ".claude" / "projects"
    assert cfg.fts5_db_path == Path("/fake/user") / ".claude" / "memory_fts5.db"
    assert cfg.costs_db_path == Path("/fake/user") / ".claude" / "memory_costs.db"


def test_l4_home_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("L4_HOME", str(tmp_path))
    cfg = l4_config.get_config()
    assert cfg.home == tmp_path
    assert cfg.costs_db_path == tmp_path / "memory_costs.db"
    assert cfg.routing_db_path == tmp_path / "routing_learner_db"
    assert cfg.semantic_db_path == tmp_path / "semantic_db_global"
    assert cfg.projects_dir == tmp_path / "projects"
    assert cfg.fts5_db_path == tmp_path / "memory_fts5.db"


def test_explicit_home_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("L4_HOME", str(tmp_path / "env"))
    explicit = tmp_path / "explicit"
    cfg = l4_config.get_config(home=explicit)
    assert cfg.home == explicit


def test_embedding_model_env_override(monkeypatch):
    monkeypatch.delenv("L4_MODEL", raising=False)
    assert l4_config.get_config().embedding_model == l4_config.DEFAULT_MODEL
    monkeypatch.setenv("L4_MODEL", "custom-model")
    assert l4_config.get_config().embedding_model == "custom-model"
