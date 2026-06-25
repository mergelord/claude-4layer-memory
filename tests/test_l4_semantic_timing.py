#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for optional semantic timing diagnostics."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class _FakeMemory:  # pylint: disable=too-few-public-methods
    """Minimal semantic memory fake for CLI timing tests."""

    def search_all(self, query):
        return [
            {
                "key": "[global] notes.md",
                "text": f"result for {query}",
                "distance": 0.1,
                "metadata": {"file": "notes.md"},
                "source": "global",
            }
        ]


def test_timing_flag_keeps_json_stdout_clean(monkeypatch, capsys):
    """--timing must emit diagnostics to stderr while stdout remains JSON."""
    module = importlib.import_module("l4_semantic_global")
    monkeypatch.setattr(module, "GlobalSemanticMemory", _FakeMemory)
    monkeypatch.setattr(
        sys,
        "argv",
        ["l4_semantic_global.py", "search-all", "test", "--json", "--timing"],
    )

    module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["results"][0]["key"] == "[global] notes.md"
    assert "[TIMING]" not in captured.out
    assert "[TIMING]" in captured.err


def test_print_results_json_has_no_timing_without_flag(capsys):
    """The JSON printer itself must not add timing diagnostics."""
    module = importlib.import_module("l4_semantic_global")
    module._SEMANTIC_TIMING_ENABLED = False  # pylint: disable=protected-access

    module._print_results(  # pylint: disable=protected-access
        [
            {
                "key": "[global] notes.md",
                "text": "body",
                "distance": 0.2,
                "metadata": {"file": "notes.md"},
                "source": "global",
            }
        ],
        json_output=True,
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out)["results"][0]["text"] == "body"
    assert captured.err == ""
