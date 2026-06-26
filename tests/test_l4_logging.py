#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the structured JSON rotating logging helpers."""

import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import l4_logging  # noqa: E402

_FLAG = "_l4_json_rotating_configured"


def _reset_root(handlers_before):
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler not in handlers_before:
            root.removeHandler(handler)
    if hasattr(root, _FLAG):
        delattr(root, _FLAG)


def test_json_formatter_emits_single_line_json():
    formatter = l4_logging.JsonFormatter()
    record = logging.LogRecord(
        name="l4.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    line = formatter.format(record)
    assert "\n" not in line
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "l4.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_configure_logging_writes_rotating_file(monkeypatch, tmp_path):
    monkeypatch.setenv("L4_HOME", str(tmp_path))
    root = logging.getLogger()
    if hasattr(root, _FLAG):
        delattr(root, _FLAG)
    handlers_before = list(root.handlers)
    try:
        l4_logging.configure_logging(level="DEBUG")
        logging.getLogger("l4.test").info("structured-entry")
        for handler in root.handlers:
            handler.flush()
        log_file = tmp_path / "logs" / "l4.log"
        assert log_file.exists()
        contents = log_file.read_text(encoding="utf-8")
        assert "structured-entry" in contents
    finally:
        _reset_root(handlers_before)


def test_configure_logging_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("L4_HOME", str(tmp_path))
    root = logging.getLogger()
    if hasattr(root, _FLAG):
        delattr(root, _FLAG)
    handlers_before = list(root.handlers)
    try:
        l4_logging.configure_logging()
        count_after_first = len(root.handlers)
        l4_logging.configure_logging()
        count_after_second = len(root.handlers)
        assert count_after_second == count_after_first
    finally:
        _reset_root(handlers_before)
