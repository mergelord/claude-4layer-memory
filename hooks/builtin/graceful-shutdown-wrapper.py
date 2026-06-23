#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Graceful Shutdown Wrapper — guarantees Stop hooks execute even on errors.

Wraps all discovered stop hooks in try-except and ensures they run
even if one fails. Uses auto-discovery: scans ~/.claude/hooks/ for
stop-*.py files.

Usage:
    Called automatically at Stop event before all other hooks.
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

HOOKS_DIR = Path.home() / ".claude" / "hooks"
TIMEOUT_SECONDS = 30


def discover_stop_hooks() -> List[str]:
    """Scan hooks directory for stop-*.py files, excluding self."""
    if not HOOKS_DIR.exists():
        return []

    self_name = Path(__file__).name
    hooks = []

    for f in sorted(HOOKS_DIR.iterdir()):
        if (f.name.startswith("stop-")
                and f.name.endswith(".py")
                and f.name != self_name
                and f.is_file()):
            hooks.append(f.name)

    return hooks


def execute_hook(hook_name: str) -> Dict:
    """Execute a single hook with error handling."""
    hook_path = HOOKS_DIR / hook_name

    if not hook_path.exists():
        return {'hook': hook_name, 'status': 'skipped', 'reason': 'file not found'}

    try:
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            encoding='utf-8',
            errors='replace',
            check=False
        )

        if result.returncode == 0:
            return {'hook': hook_name, 'status': 'success', 'stdout': result.stdout, 'stderr': result.stderr}
        return {
            'hook': hook_name,
            'status': 'failed',
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }

    except subprocess.TimeoutExpired:
        logging.error("Hook %s timed out after %ds", hook_name, TIMEOUT_SECONDS)
        return {'hook': hook_name, 'status': 'timeout', 'reason': f'exceeded {TIMEOUT_SECONDS}s timeout'}

    except Exception as exc:
        logging.error("Hook %s error: %s", hook_name, exc)
        return {'hook': hook_name, 'status': 'error', 'error': str(exc)}


def run_all_hooks() -> List[Dict]:
    """Discover and execute all stop hooks."""
    hooks = discover_stop_hooks()
    results = []

    if not hooks:
        logging.info("No stop-*.py hooks found in %s", HOOKS_DIR)
        return results

    logging.info("Discovered %d stop hooks: %s", len(hooks), ", ".join(hooks))

    for hook_name in hooks:
        logging.info("Executing %s...", hook_name)
        result = execute_hook(hook_name)
        results.append(result)

        if result['status'] == 'success':
            logging.info("  ✓ %s completed", hook_name)
        elif result['status'] == 'skipped':
            logging.warning("  ⊘ %s skipped: %s", hook_name, result['reason'])
        else:
            logging.error("  ✗ %s failed: %s", hook_name, result.get('reason', result.get('error', 'unknown')))

    return results


def save_execution_log(results: List[Dict]) -> None:
    """Append execution results to log file for debugging."""
    log_file = Path.home() / ".claude" / ".stop_hooks_execution.log"

    try:
        import json
        from datetime import datetime, timezone

        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'results': results
        }

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    except Exception as exc:
        logging.warning("Failed to save execution log: %s", exc)


def main() -> int:
    """CLI entry point. Always returns 0 to not block session exit."""
    try:
        results = run_all_hooks()
        save_execution_log(results)

        failed = sum(1 for r in results if r['status'] in ('failed', 'error', 'timeout'))
        success = sum(1 for r in results if r['status'] == 'success')

        if failed > 0:
            logging.warning("Completed with %d failures, %d successes", failed, success)
        else:
            logging.info("All %d hooks completed successfully", success)

    except Exception as exc:
        logging.error("Graceful shutdown failed: %s", exc)

    return 0


if __name__ == '__main__':
    sys.exit(main())
