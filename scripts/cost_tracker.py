#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cost Tracker для Memory Operations
Отслеживает расход токенов на операции с памятью
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


class CostTracker:
    """Отслеживание стоимости операций с памятью"""

    # Примерные цены за 1M токенов (USD)
    PRICES = {
        'claude-opus-4': {'input': 15.0, 'output': 75.0},
        'claude-sonnet-4': {'input': 3.0, 'output': 15.0},
        'claude-haiku-4': {'input': 0.25, 'output': 1.25},
        'embedding': {'input': 0.1, 'output': 0.0}  # sentence-transformers локально
    }

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            claude_dir = Path.home() / ".claude"
            db_path = claude_dir / "memory_costs.db"

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Инициализация БД"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    input_cost REAL DEFAULT 0.0,
                    output_cost REAL DEFAULT 0.0,
                    total_cost REAL DEFAULT 0.0,
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

    @contextmanager
    def _get_connection(self):
        """Context manager для SQLite соединения"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def track_operation(
        self,
        operation_type: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = 'claude-sonnet-4',
        metadata: Optional[str] = None
    ) -> Dict[str, Any]:
        """Записывает операцию и возвращает стоимость"""

        # Вычисляем стоимость
        prices = self.PRICES.get(model, self.PRICES['claude-sonnet-4'])
        input_cost = (input_tokens / 1_000_000) * prices['input']
        output_cost = (output_tokens / 1_000_000) * prices['output']
        total_cost = input_cost + output_cost

        timestamp = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO operations (
                    timestamp, operation_type, model,
                    input_tokens, output_tokens,
                    input_cost, output_cost, total_cost,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, operation_type, model,
                input_tokens, output_tokens,
                input_cost, output_cost, total_cost,
                metadata
            ))

            operation_id = cursor.lastrowid

        return {
            'id': operation_id,
            'timestamp': timestamp,
            'operation_type': operation_type,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': total_cost
        }

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Статистика за последние N дней"""
        with self._get_connection() as conn:
            # Общая статистика
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_operations,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_cost) as total_cost
                FROM operations
                WHERE timestamp >= datetime('now', '-' || ? || ' days')
            """, (days,)).fetchone()

            # По типам операций
            operations_by_type = {}
            for op_row in conn.execute("""
                SELECT
                    operation_type,
                    COUNT(*) as count,
                    SUM(total_cost) as cost
                FROM operations
                WHERE timestamp >= datetime('now', '-' || ? || ' days')
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
                'total_cost': row['total_cost'] or 0.0,
                'operations_by_type': operations_by_type
            }

    def print_stats(self, days: int = 7):
        """Выводит статистику в консоль"""
        stats = self.get_stats(days)

        print(f"\n[COST STATISTICS] Last {days} days")
        print("=" * 60)
        print(f"Total operations: {stats['total_operations']}")
        print(f"Total tokens: {stats['total_input_tokens'] + stats['total_output_tokens']:,}")
        print(f"  Input:  {stats['total_input_tokens']:,}")
        print(f"  Output: {stats['total_output_tokens']:,}")
        print(f"Total cost: ${stats['total_cost']:.4f}")

        if stats['operations_by_type']:
            print("\nBy operation type:")
            for op_type, data in stats['operations_by_type'].items():
                print(f"  {op_type:30s} {data['count']:4d} ops  ${data['cost']:.4f}")


def main():
    """CLI интерфейс"""
    import argparse

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
    parser.add_argument('--model', type=str, default='claude-sonnet-4',
                        help='Model name')

    args = parser.parse_args()
    tracker = CostTracker()

    if args.command == 'stats':
        tracker.print_stats(args.days)

    elif args.command == 'track':
        if not args.operation:
            print("[ERROR] --operation required for track command")
            sys.exit(1)

        result = tracker.track_operation(
            operation_type=args.operation,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            model=args.model
        )

        print(f"[TRACKED] {result['operation_type']}")
        print(f"  Tokens: {result['input_tokens']} in, {result['output_tokens']} out")
        print(f"  Cost: ${result['total_cost']:.6f}")


if __name__ == '__main__':
    main()
