#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for lazy l4_rerank loading in the FTS5 CLI."""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def test_import_l4_fts5_search_does_not_import_l4_rerank(monkeypatch):
    monkeypatch.delitem(sys.modules, "l4_fts5_search", raising=False)
    monkeypatch.delitem(sys.modules, "l4_rerank", raising=False)

    importlib.import_module("l4_fts5_search")

    assert "l4_rerank" not in sys.modules


def test_get_l4_rerank_imports_on_demand(monkeypatch):
    module = importlib.import_module("l4_fts5_search")
    module._get_l4_rerank.cache_clear()

    fake_rerank = MagicMock(name="rerank")
    fake_module = types.SimpleNamespace(rerank=fake_rerank)
    monkeypatch.setitem(sys.modules, "l4_rerank", fake_module)

    assert module._get_l4_rerank() is fake_rerank
