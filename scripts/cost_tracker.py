#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cost Tracker for Memory Operations

Tracks token consumption with authoritative API usage, including
Claude prompt caching (cache_creation / cache_read) and per-model
pricing with safe fallbacks.
"""

import argparse
import codecs
import sys
import sqlite3
import json
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from contextlib import contextmanager

CACHE_CREATION_PRICE_KEY = "cache_creation_input"
CACHE_READ_PRICE_KEY = "cache_read_input"


def configure_utf8_output() -> None:
    """Force UTF-8 console output on Windows when the script runs as a CLI."""
    if sys.platform != "win32":
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        encoding = str(getattr(stream, "encoding", None) or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue

        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="strict")
                continue
            except (AttributeError, OSError, ValueError):
                pass

        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            setattr(sys, stream_name, codecs.getwriter("utf-8")(buffer, "strict"))


class CostTracker:
    """Token cost tracking with Claude prompt-cache support.

    Prices include cache tiers (creation = 1.25× input, read = 0.10× input)
    and degrade safely when models or config keys are missing.
    """

    DEFAULT_PRICES = {
        'claude-opus-4': {
            'input': 15.0,
            'output': 75.0,
            CACHE_CREATION_PRICE_KEY: 18.75,
            CACHE_READ_PRICE_KEY: 1.50,
        },
        'claude-sonnet-4': {
            'input': 3.0,
            'output': 15.0,
            CACHE_CREATION_PRICE_KEY: 3.75,
            CACHE_READ_PRICE_KEY: 0.30,
        },
        'claude-haiku-4': {
            'input': 0.25,
            'output': 1.25,
            CACHE_CREATION_PRICE_KEY: 0.30,
            CACHE_READ_PRICE_KEY: 0.03,
        },
        'embedding': {'input': 0.1, 'output': 0.0}
    }

    FALLBACK_MODEL = 'claude-sonnet-4'

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            claude_dir = Path.home() / ".claude"
            db_path = claude_dir / "memory_costs.db"

        self.db_path = self._safe_db_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.prices = self._load_prices()
        self._init_db()

    def _safe_db_path(self, path: Path) -> Path:
        """Validate database path is within allowed directories."""
        try:
            resolved = path.resolve()
            home = Path.home().resolve()
            tmp = Path(tempfile.gettempdir()).resolve()
            if not (resolved.is_relative_to(home) or resolved.is_relative_to(tmp)):
                raise ValueError(
                    f"Database path must be within home or temp directory: {path}"
                )
            return resolved
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Invalid database path: {path}") from exc

    def _load_prices(self) -> Dict[str, Dict[str, float]]:
        """Load prices from config file or use defaults"""
        prices_file = Path(__file__).parent.parent / "config" / "prices.json"

        if prices_file.exists() and os.access(prices_file, os.R_OK):
            try:
                with open(prices_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"[WARN] Failed to load prices.json: {e}", file=sys.stderr)
                print("[WARN] Using default prices", file=sys.stderr)

        return self.DEFAULT_PRICES

    def _resolve_price(self, model: str) -> Dict[str, float]:
        """Return prices for a model with safe fallbacks."""
        fallback = self.DEFAULT_PRICES.get(
            self.FALLBACK_MODEL, {'input': 0.0, 'output': 0.0}
        )
        price = (
            self.prices.get(model)
            or self.prices.get(self.FALLBACK_MODEL)
            or fallback
        )
        return {
            'input': float(price.get('input', fallback.get('input', 0.0))),
            'output': float(price.get('output', fallback.get('output', 0.0))),
            CACHE_CREATION_PRICE_KEY: float(
                price.get(
                    CACHE_CREATION_PRICE_KEY,
                    fallback.get(CACHE_CREATION_PRICE_KEY, 0.0),
                )
            ),
            CACHE_READ_PRICE_KEY: float(
                price.get(
                    CACHE_READ_PRICE_KEY,
                    fallback.get(CACHE_READ_PRICE_KEY, 0.0),
                )
            ),
        }

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cache_creation_input_tokens INTEGER DEFAULT 0,
                    cache_read_input_tokens INTEGER DEFAULT 0,
                    input_cost REAL DEFAULT 0.0,
                    output_cost REAL DEFAULT 0.0,
                    cache_creation_cost REAL DEFAULT 0.0,
                    cache_read_cost REAL DEFAULT 0.0,
                    total_cost REAL DEFAULT 0.0,
                    request_id TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON operations(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_operation_type
                ON operations(operation_type)
            """)

            self._ensure_optional_columns(conn)

    @staticmethod
    def _ensure_optional_columns(conn: sqlite3.Connection) -> None:
        """Add columns to databases created by older versions."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(operations)")}
        optional_columns = {
            "cache_creation_input_tokens": "INTEGER DEFAULT 0",
            "cache_read_input_tokens": "INTEGER DEFAULT 0",
            "cache_creation_cost": "REAL DEFAULT 0.0",
            "cache_read_cost": "REAL DEFAULT 0.0",
            "request_id": "TEXT",
        }
        for column, definition in optional_columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE operations ADD COLUMN {column} {definition}")

    @contextmanager
    def _get_connection(self):
        """Context manager for SQLite connection with WAL and retry."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:  # nosec
            pass
        try:
            yield conn
            self._commit_with_retry(conn)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _commit_with_retry(
        conn: sqlite3.Connection,
        *,
        retries: int = 3,
        delay: float = 0.1,
    ) -> None:
        """Commit with retry for transient database-is-locked errors."""
        for attempt in range(retries):
            try:
                conn.commit()
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                is_locked = (
                    "database is locked" in message
                    or "database is busy" in message
                )
                if not is_locked or attempt == retries - 1:
                    raise
                time.sleep(delay)

    def track_operation(
        self,
        operation_type: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        model: str = 'claude-sonnet-4',
        request_id: Optional[str] = None,
        metadata: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record an operation and return its cost breakdown."""
        prices = self._resolve_price(model)
        input_cost = (input_tokens / 1_000_000) * prices['input']
        output_cost = (output_tokens / 1_000_000) * prices['output']
        cache_creation_cost = (
            cache_creation_input_tokens / 1_000_000
        ) * prices[CACHE_CREATION_PRICE_KEY]
        cache_read_cost = (
            cache_read_input_tokens / 1_000_000
        ) * prices[CACHE_READ_PRICE_KEY]
        total_cost = input_cost + output_cost + cache_creation_cost + cache_read_cost

        timestamp = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO operations (
                    timestamp, operation_type, model,
                    input_tokens, output_tokens,
                    cache_creation_input_tokens, cache_read_input_tokens,
                    input_cost, output_cost,
                    cache_creation_cost, cache_read_cost,
                    total_cost, request_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, operation_type, model,
                input_tokens, output_tokens,
                cache_creation_input_tokens, cache_read_input_tokens,
                input_cost, output_cost,
                cache_creation_cost, cache_read_cost,
                total_cost, request_id, metadata
            ))

            operation_id = cursor.lastrowid

        return {
            'id': operation_id,
            'timestamp': timestamp,
            'operation_type': operation_type,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_creation_input_tokens': cache_creation_input_tokens,
            'cache_read_input_tokens': cache_read_input_tokens,
            'input_cost': input_cost,
            'output_cost': output_cost,
            'cache_creation_cost': cache_creation_cost,
            'cache_read_cost': cache_read_cost,
            'total_cost': total_cost,
            'request_id': request_id,
        }

    @staticmethod
    def _usage_value(usage: Any, key: str) -> int:
        """Read Anthropic SDK usage fields from objects or dictionaries."""
        value = usage.get(key, 0) if isinstance(usage, dict) else getattr(usage, key, 0)
        return int(value or 0)

    def track_claude_usage(
        self,
        operation_type: str,
        *,
        model: str,
        usage: Any,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Track exact Claude token usage from an Anthropic API response."""
        metadata_json = (
            json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            if metadata is not None
            else None
        )
        return self.track_operation(
            operation_type=operation_type,
            model=model,
            input_tokens=self._usage_value(usage, "input_tokens"),
            output_tokens=self._usage_value(usage, "output_tokens"),
            cache_creation_input_tokens=self._usage_value(
                usage, "cache_creation_input_tokens"
            ),
            cache_read_input_tokens=self._usage_value(usage, "cache_read_input_tokens"),
            request_id=request_id,
            metadata=metadata_json,
        )

    def track_claude_message(
        self,
        operation_type: str,
        message: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Track exact usage from a full Anthropic message response object."""
        if isinstance(message, dict):
            model = message.get("model", self.FALLBACK_MODEL)
            usage = message.get("usage")
            request_id = message.get("id")
        else:
            model = getattr(message, "model", self.FALLBACK_MODEL)
            usage = getattr(message, "usage", None)
            request_id = getattr(message, "id", None)

        if usage is None:
            raise ValueError("Claude message response does not contain usage")

        return self.track_claude_usage(
            operation_type=operation_type,
            model=model,
            usage=usage,
            request_id=request_id,
            metadata=metadata,
        )

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Statistics for the last N days (UTC)."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_operations,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(cache_creation_input_tokens) as total_cache_creation_input_tokens,
                    SUM(cache_read_input_tokens) as total_cache_read_input_tokens,
                    SUM(total_cost) as total_cost
                FROM operations
                WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' days')
            """, (days,)).fetchone()

            operations_by_type = {}
            for op_row in conn.execute("""
                SELECT
                    operation_type,
                    COUNT(*) as count,
                    SUM(total_cost) as cost
                FROM operations
                WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' days')
                GROUP BY operation_type
                ORDER BY cost DESC
            """, (days,)):
                operations_by_type[op_row['operation_type']] = {
                    'count': op_row['count'],
                    'cost': op_row['cost']
                }

            return {
                'period_days': days,
                'total_operations': row['total_operations'] or 0,
                'total_input_tokens': row['total_input_tokens'] or 0,
                'total_output_tokens': row['total_output_tokens'] or 0,
                'total_cache_creation_input_tokens': (
                    row['total_cache_creation_input_tokens'] or 0
                ),
                'total_cache_read_input_tokens': row['total_cache_read_input_tokens'] or 0,
                'total_cost': row['total_cost'] or 0.0,
                'operations_by_type': operations_by_type
            }

    @staticmethod
    def _row_to_operation(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert an operations row to a JSON-compatible dictionary."""
        metadata = row["metadata"]
        try:
            parsed_metadata = json.loads(metadata) if metadata else None
        except json.JSONDecodeError:
            parsed_metadata = metadata
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "operation_type": row["operation_type"],
            "model": row["model"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "cache_creation_input_tokens": row["cache_creation_input_tokens"] or 0,
            "cache_read_input_tokens": row["cache_read_input_tokens"] or 0,
            "total_cost": row["total_cost"] or 0.0,
            "request_id": row["request_id"],
            "metadata": parsed_metadata,
        }

    def get_recent_operations(self, limit: int = 20) -> list[Dict[str, Any]]:
        """Return most recent cost rows for task-level inspection."""
        safe_limit = max(1, min(int(limit), 100))
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM operations
                ORDER BY datetime(timestamp) DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._row_to_operation(row) for row in rows]

    def get_stats_by_metadata_key(
        self,
        key: str,
        days: int = 7,
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate recent cost rows by a JSON metadata key, e.g. 'task'."""
        grouped: Dict[str, Dict[str, Any]] = {}
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM operations
                WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' days')
                """,
                (days,),
            ).fetchall()

        for row in rows:
            operation = self._row_to_operation(row)
            metadata = operation.get("metadata")
            group_value = "<missing>"
            if isinstance(metadata, dict) and metadata.get(key) is not None:
                group_value = str(metadata[key])
            bucket = grouped.setdefault(
                group_value,
                {
                    "count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "total_cost": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["input_tokens"] += operation["input_tokens"]
            bucket["output_tokens"] += operation["output_tokens"]
            bucket["cache_creation_input_tokens"] += operation[
                "cache_creation_input_tokens"
            ]
            bucket["cache_read_input_tokens"] += operation["cache_read_input_tokens"]
            bucket["total_cost"] += operation["total_cost"]

        return dict(
            sorted(
                grouped.items(),
                key=lambda item: item[1]["total_cost"],
                reverse=True,
            )
        )

    def get_model_breakdown(self, days: int = 7) -> Dict[str, Dict[str, Any]]:
        """Aggregate costs by model for the last N days."""
        grouped: Dict[str, Dict[str, Any]] = {}
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    model,
                    COUNT(*) as count,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(cache_creation_input_tokens) as cache_creation,
                    SUM(cache_read_input_tokens) as cache_read,
                    SUM(total_cost) as total_cost
                FROM operations
                WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' days')
                  AND model IS NOT NULL
                GROUP BY model
                ORDER BY total_cost DESC
                """,
                (days,),
            ).fetchall()

        for row in rows:
            grouped[row["model"]] = {
                "count": row["count"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "cache_creation_tokens": row["cache_creation"] or 0,
                "cache_read_tokens": row["cache_read"] or 0,
                "total_cost": row["total_cost"] or 0.0,
            }
        return grouped

    def print_stats(self, days: int = 7, verbose: bool = False):
        """Print cost statistics to console."""
        stats = self.get_stats(days)

        print(f"\n[COST STATISTICS] Last {days} days")
        print("=" * 60)
        print(f"Total operations: {stats['total_operations']}")
        print(f"Total tokens: {stats['total_input_tokens'] + stats['total_output_tokens']:,}")
        print(f"  Input:  {stats['total_input_tokens']:,}")
        print(f"  Output: {stats['total_output_tokens']:,}")
        print(
            "  Cache:  "
            f"{stats['total_cache_creation_input_tokens']:,} created, "
            f"{stats['total_cache_read_input_tokens']:,} read"
        )
        print(f"Total cost: ${stats['total_cost']:.4f}")

        if stats['operations_by_type']:
            print("\nBy operation type:")
            for op_type, data in stats['operations_by_type'].items():
                print(f"  {op_type:30s} {data['count']:4d} ops  ${data['cost']:.4f}")

        # Model breakdown (new)
        model_breakdown = self.get_model_breakdown(days)
        if model_breakdown:
            print("\nBy model:")
            for model_name, data in model_breakdown.items():
                print(
                    f"  {model_name:25s} {data['count']:4d} calls  "
                    f"${data['total_cost']:.4f}"
                )

        if verbose:
            print("\n[VERBOSE] Price configuration:")
            for model, prices in self.prices.items():
                inp = prices.get('input', 0.0)
                out = prices.get('output', 0.0)
                cache_create = prices.get(CACHE_CREATION_PRICE_KEY, 0.0)
                cache_read = prices.get(CACHE_READ_PRICE_KEY, 0.0)
                print(
                    f"  {model:20s} Input: ${inp:.2f}/M  "
                    f"Output: ${out:.2f}/M  "
                    f"Cache create/read: ${cache_create:.2f}/${cache_read:.2f}/M"
                )


def main():
    """CLI interface."""
    configure_utf8_output()

    parser = argparse.ArgumentParser(description='Memory Cost Tracker')
    parser.add_argument('command', choices=['stats', 'track'],
                        help='Command to execute')
    parser.add_argument('--days', type=int, default=7,
                        help='Days for stats (default: 7)')
    parser.add_argument('--operation', type=str,
                        help='Operation type for tracking')
    parser.add_argument('--input-tokens', type=int, default=0,
                        help='Input tokens')
    parser.add_argument('--output-tokens', type=int, default=0,
                        help='Output tokens')
    parser.add_argument('--cache-creation-input-tokens', type=int, default=0,
                        help='Claude prompt cache creation input tokens')
    parser.add_argument('--cache-read-input-tokens', type=int, default=0,
                        help='Claude prompt cache read input tokens')
    parser.add_argument('--request-id', type=str,
                        help='Provider request/message ID')
    parser.add_argument('--model', type=str, default='claude-sonnet-4',
                        help='Model name')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed output')

    args = parser.parse_args()
    tracker = CostTracker()

    if args.command == 'stats':
        tracker.print_stats(args.days, verbose=args.verbose)

    elif args.command == 'track':
        if not args.operation:
            print("[ERROR] --operation required for track command")
            sys.exit(1)

        result = tracker.track_operation(
            operation_type=args.operation,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            cache_creation_input_tokens=args.cache_creation_input_tokens,
            cache_read_input_tokens=args.cache_read_input_tokens,
            request_id=args.request_id,
            model=args.model,
        )

        print(f"[TRACKED] {result['operation_type']}")
        print(f"  Tokens: {result['input_tokens']} in, {result['output_tokens']} out")
        print(
            "  Cache: "
            f"{result['cache_creation_input_tokens']} created, "
            f"{result['cache_read_input_tokens']} read"
        )
        print(f"  Cost: ${result['total_cost']:.6f}")

        if args.verbose:
            print(f"  Model: {result['model']}")
            print(f"  Timestamp: {result['timestamp']}")
            print(f"  ID: {result['id']}")
            if result['request_id']:
                print(f"  Request ID: {result['request_id']}")


if __name__ == '__main__':
    main()
