#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stop-хук: сбор РЕАЛЬНОГО usage сессии из транскрипта в SQLite.

Принцип: пишем только измеренные значения из ``message.usage`` транскрипта.
Никаких долларовых проекций, никаких оценок «по длине сессии».
Источник данных — поля, которые клиент Claude Code уже записал в .jsonl:
``input_tokens``, ``output_tokens``, ``cache_creation_input_tokens``,
``cache_read_input_tokens``.

Хук читает JSON со stdin (Stop hook payload), берёт ``transcript_path`` и
``session_id``. Любая ошибка логируется и проглатывается — сбор статистики
не должен ронять завершение сессии.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="[session-usage-logger] %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

DB_PATH: Path = Path.home() / ".claude" / "session_usage.db"

USAGE_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def read_hook_payload() -> dict[str, Any]:
    """Читает JSON Stop-хука со stdin.

    Returns:
        Распарсенный payload или пустой dict, если stdin пуст/не JSON.
    """
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("stdin не JSON: %s", exc)
        return {}


def aggregate_usage(transcript_path: Path) -> dict[str, Any]:
    """Суммирует реальный usage по всем сообщениям транскрипта.

    Args:
        transcript_path: Путь к .jsonl транскрипту сессии.

    Returns:
        dict с суммами по полям USAGE_FIELDS, числом сообщений с usage и
        последней встреченной моделью (``message.model``).
    """
    totals: dict[str, int] = {field: 0 for field in USAGE_FIELDS}
    messages_with_usage = 0
    model: str | None = None

    with transcript_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            messages_with_usage += 1
            if message.get("model"):
                model = message["model"]
            for field in USAGE_FIELDS:
                value = usage.get(field)
                if isinstance(value, int):
                    totals[field] += value

    totals["messages_with_usage"] = messages_with_usage
    totals["model"] = model
    return totals


def init_db(db_path: Path) -> None:
    """Создаёт таблицу session_usage, если её нет."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                model TEXT,
                messages_with_usage INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_creation_input_tokens INTEGER DEFAULT 0,
                cache_read_input_tokens INTEGER DEFAULT 0,
                transcript_path TEXT,
                UNIQUE(session_id)
            )
            """
        )


def write_usage(
    db_path: Path,
    session_id: str | None,
    transcript_path: Path,
    totals: dict[str, Any],
) -> None:
    """Записывает агрегат сессии. UPSERT по session_id (идемпотентно)."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """
            INSERT INTO session_usage (
                session_id, timestamp, model, messages_with_usage,
                input_tokens, output_tokens,
                cache_creation_input_tokens, cache_read_input_tokens,
                transcript_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                timestamp=excluded.timestamp,
                model=excluded.model,
                messages_with_usage=excluded.messages_with_usage,
                input_tokens=excluded.input_tokens,
                output_tokens=excluded.output_tokens,
                cache_creation_input_tokens=excluded.cache_creation_input_tokens,
                cache_read_input_tokens=excluded.cache_read_input_tokens,
                transcript_path=excluded.transcript_path
            """,
            (
                session_id,
                timestamp,
                totals.get("model"),
                totals.get("messages_with_usage", 0),
                totals.get("input_tokens", 0),
                totals.get("output_tokens", 0),
                totals.get("cache_creation_input_tokens", 0),
                totals.get("cache_read_input_tokens", 0),
                str(transcript_path),
            ),
        )


def main() -> None:
    """Точка входа Stop-хука."""
    payload = read_hook_payload()
    transcript_raw = payload.get("transcript_path")
    session_id = payload.get("session_id")

    if not transcript_raw:
        logger.info("transcript_path отсутствует в payload — нечего собирать")
        return

    transcript_path = Path(transcript_raw)
    if not transcript_path.is_file():
        logger.info("транскрипт не найден: %s", transcript_path)
        return

    try:
        totals = aggregate_usage(transcript_path)
        init_db(DB_PATH)
        write_usage(DB_PATH, session_id, transcript_path, totals)
        logger.info(
            "записано: out=%s in=%s cache_read=%s msgs=%s model=%s",
            totals.get("output_tokens"),
            totals.get("input_tokens"),
            totals.get("cache_read_input_tokens"),
            totals.get("messages_with_usage"),
            totals.get("model"),
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("сбор usage не удался: %s", exc)


if __name__ == "__main__":
    main()
