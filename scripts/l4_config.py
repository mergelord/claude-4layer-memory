#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for L4 memory filesystem paths and core settings.

Historically each module hardcoded ``~/.claude/...`` and read ``Path.home()``
directly, which made the system awkward to relocate for tests, deployment, or
running several isolated instances. This module centralizes the layout behind
one :class:`L4Config` rooted at ``L4_HOME`` (default ``~/.claude``).

Backward compatibility is intentional: with no ``L4_HOME`` set, every derived
path is exactly what the modules used before (``~/.claude/memory_fts5.db`` and
friends), so there is no data migration. Modules still accept explicit path
arguments; the config only supplies the default when an argument is omitted.
"""

from __future__ import annotations

import os
from pathlib import Path

# Default sentence-transformers model. Kept here so path/model configuration
# lives in one place; modules may still read ``L4_MODEL`` directly.
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Environment variable that relocates the entire memory home.
HOME_ENV_VAR = "L4_HOME"


def _resolve_home(explicit: str | Path | None = None) -> Path:
    """Resolve the memory home directory.

    Priority: explicit argument > ``L4_HOME`` env var > ``~/.claude``.
    The env var / ``Path.home()`` are read here (at call time) so tests that
    monkeypatch either before constructing a config observe the expected
    value, matching the previous instance-time ``Path.home()`` reads.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env_home = os.getenv(HOME_ENV_VAR)
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".claude"


class L4Config:
    """Resolved filesystem layout and core settings for the memory system."""

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = _resolve_home(home)

    @property
    def memory_dir(self) -> Path:
        """Markdown memory root (``<home>/memory``)."""
        return self.home / "memory"

    @property
    def projects_dir(self) -> Path:
        """Per-project memory root (``<home>/projects``)."""
        return self.home / "projects"

    @property
    def fts5_db_path(self) -> Path:
        """SQLite FTS5 index (``<home>/memory_fts5.db``)."""
        return self.home / "memory_fts5.db"

    @property
    def semantic_db_path(self) -> Path:
        """ChromaDB persistent dir for global semantic memory."""
        return self.home / "semantic_db_global"

    @property
    def costs_db_path(self) -> Path:
        """SQLite cost ledger (``<home>/memory_costs.db``)."""
        return self.home / "memory_costs.db"

    @property
    def routing_db_path(self) -> Path:
        """ChromaDB persistent dir for the routing learner."""
        return self.home / "routing_learner_db"

    @property
    def logs_dir(self) -> Path:
        """Structured log output directory (``<home>/logs``).

        Hosts the rotating JSON log written by :mod:`l4_logging`. Like every
        other path here it is derived from ``home`` so relocating ``L4_HOME``
        moves logs alongside the rest of the memory state.
        """
        return self.home / "logs"

    @property
    def embedding_model(self) -> str:
        """Sentence-transformers model name (``L4_MODEL`` env override)."""
        return os.getenv("L4_MODEL", DEFAULT_MODEL)

    def __repr__(self) -> str:
        return f"L4Config(home={self.home!r})"


def get_config(home: str | Path | None = None) -> L4Config:
    """Return a fresh :class:`L4Config`.

    A new instance is returned per call (cheap) so env / ``Path.home()``
    changes between calls are always honoured -- important for tests that
    monkeypatch the home directory after import.
    """
    return L4Config(home=home)
