#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for Windows stdio compatibility.

The MCP stdio transport expects the original sys.stdout object to expose
``.buffer``. ``l4_fts5_search`` used to rewrap stdout/stderr at import time on
Windows, which broke ``python mcp_server.py`` before FastMCP could start.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class _FakeTextStream:  # pylint: disable=too-few-public-methods
    """Tiny stream stand-in with the attributes import-time code might touch."""

    def __init__(self) -> None:
        self.buffer = object()
        self.writes: list[str] = []

    def write(self, data: str) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        """Match the TextIO stream protocol enough for logging handlers."""


def test_importing_l4_fts5_search_does_not_replace_windows_stdio(monkeypatch):
    """Importing the search module must not mutate stdout/stderr on Windows."""
    old_module = sys.modules.pop("l4_fts5_search", None)
    fake_stdout = _FakeTextStream()
    fake_stderr = _FakeTextStream()

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    try:
        importlib.import_module("l4_fts5_search")
        assert sys.stdout is fake_stdout
        assert sys.stderr is fake_stderr
    finally:
        sys.modules.pop("l4_fts5_search", None)
        if old_module is not None:
            sys.modules["l4_fts5_search"] = old_module
