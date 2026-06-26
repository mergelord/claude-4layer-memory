#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured JSON logging with rotation for the L4 memory system.

Provides a small, dependency-free logging setup shared by runtime entrypoints
(e.g. the MCP server). Logs are written as one JSON object per line to a
rotating file under ``L4Config.logs_dir`` so they can be ingested by log
tooling without bespoke parsing, while console output configured elsewhere is
left untouched.

The setup is intentionally side-effect free at import time: no handler is
attached until :func:`configure_logging` is called explicitly (so importing
this module in tests or other modules stays cheap and predictable).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Imported after the sys.path bootstrap so the flat ``scripts/`` module resolves
# at runtime without an installed package (mirrors l4_hybrid_search.py). Pylint
# analyzes statically and cannot resolve the sibling module, so suppress only
# the import-position and unresolved-import checks for this shim.
# pylint: disable=wrong-import-position,import-error
from l4_config import get_config  # noqa: E402

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 3
_LOG_FILE_NAME = "l4.log"
_CONFIGURED_FLAG = "_l4_json_rotating_configured"


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _resolve_level(level: Optional[object] = None) -> int:
    """Resolve a logging level int from an argument or ``L4_LOG_LEVEL``."""
    if level is None:
        level = os.getenv("L4_LOG_LEVEL", "INFO")
    if isinstance(level, int):
        return level
    candidate = getattr(logging, str(level).upper().strip(), None)
    return candidate if isinstance(candidate, int) else logging.INFO


def configure_logging(*, level: Optional[object] = None) -> logging.Logger:
    """Attach a rotating JSON file handler to the root logger once.

    Idempotent: repeated calls never stack duplicate handlers (guarded by a
    flag stored on the root logger). Filesystem failures (e.g. an unwritable
    logs directory) are swallowed so logging setup never crashes a runtime
    entrypoint -- any console logging configured elsewhere keeps working.
    """
    resolved_level = _resolve_level(level)
    root = logging.getLogger()
    root.setLevel(resolved_level)

    if getattr(root, _CONFIGURED_FLAG, False):
        return root

    try:
        logs_dir = get_config().logs_dir
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            logs_dir / _LOG_FILE_NAME,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(JsonFormatter())
        handler.setLevel(resolved_level)
        root.addHandler(handler)
        setattr(root, _CONFIGURED_FLAG, True)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "JSON file logging disabled: %s", exc
        )
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (thin convenience wrapper)."""
    return logging.getLogger(name)
