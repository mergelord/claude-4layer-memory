#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Search Hook для Claude Code
Проверяет триггерные слова и добавляет контекст из L4 SEMANTIC
"""

import sys
import os
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

# Импорт cost tracker
sys.path.insert(0, str(Path(__file__).parent))
try:
    from cost_tracker import CostTracker
    COST_TRACKING_ENABLED = True
except ImportError:
    COST_TRACKING_ENABLED = False

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except (AttributeError, ValueError):
        pass

# Конфигурация
SEMANTIC_SEARCH_TIMEOUT_SECONDS = 30

CONFIG: Dict[str, Any] = {
    'log_file': os.path.expanduser("~/.claude/hooks/semantic_search.log"),
    'l4_script': os.path.expanduser("~/.claude/hooks/l4_semantic_global.py"),
    'encoding': 'utf-8',
    'max_prompt_log_length': 100
}

# Триггерные фразы и паттерны
TRIGGERS = [
    "как мы", "почему мы", "раньше", "помнишь", "что мы решили",
    "какое решение", "история", "в прошлый раз", "что мы",
    "how did we", "why did we", "previously", "last time",
    "remember", "what did we decide", "history",
    "my project", "my code", "my script", "my system", "my bug",
    "our project", "our code", "our system", "our approach",
    "the project", "the script", "the bug", "the issue", "the problem",
    "the solution", "the approach", "the system", "the code",
    "you recommended", "you suggested", "you said", "you mentioned",
    "we discussed", "we decided", "we agreed", "we implemented",
    "you helped", "you fixed", "you created", "you wrote",
    "ты рекомендовал", "ты предложил", "ты говорил", "ты упоминал",
    "мы обсуждали", "мы решили", "мы согласились", "мы реализовали",
    "ты помог", "ты исправил", "ты создал", "ты написал"
]

TRIGGERS_SET = set(TRIGGERS)
TRIGGERS_LOWER = {trigger.lower() for trigger in TRIGGERS}


def safe_path(path: str) -> Path:
    """Валидация пути - должен быть внутри home directory"""
    resolved = Path(path).resolve()
    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
        return resolved
    except ValueError as exc:
        raise ValueError(f"Path {path} is outside home directory") from exc


def should_search(prompt: str) -> Tuple[bool, str]:
    """Проверяет, нужен ли семантический поиск"""
    prompt_lower = prompt.lower()
    for trigger in TRIGGERS_LOWER:
        if trigger in prompt_lower:
            return True, trigger
    return False, ""


def read_user_prompt() -> str:
    """Read user prompt from stdin with proper encoding"""
    if sys.platform == 'win32':
        try:
            raw = sys.stdin.buffer.read()
        except AttributeError:
            return sys.stdin.read().strip()
        for encoding in ('utf-8', 'cp1251', 'latin-1'):
            try:
                return raw.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace').strip()
    return sys.stdin.read().strip()


def log_trigger(user_prompt: str, trigger_found: str) -> None:
    """Log trigger activation to file"""
    try:
        log_file = safe_path(CONFIG['log_file'])
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if log_file.exists() and not os.access(log_file, os.W_OK):
            logging.warning("No write access to log file: %s", log_file)
        else:
            with open(log_file, 'a', encoding=CONFIG['encoding']) as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                max_len = CONFIG['max_prompt_log_length']
                if len(user_prompt) > max_len:
                    prompt_preview = user_prompt[:max_len] + "..."
                else:
                    prompt_preview = user_prompt
                f.write(
                    f"[{timestamp}] "
                    f"Trigger: '{trigger_found}' | "
                    f"Prompt: {prompt_preview}\n"
                )
    except (OSError, IOError, ValueError) as e:
        logging.debug("Logging failed: %s", e)


def track_search_cost(user_prompt: str, result_stdout: str, trigger_found: str) -> None:
    """Track cost of semantic search operation"""
    if not COST_TRACKING_ENABLED:
        return
    try:
        tracker = CostTracker()
        input_tokens = int(len(user_prompt.split()) * 1.3)
        output_tokens = int(len(result_stdout.split()) * 1.3) if result_stdout else 0
        tracker.track_operation(
            operation_type='semantic_search',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model='embedding',
            metadata=f"trigger: {trigger_found}"
        )
    except Exception as e:
        logging.debug("Cost tracking failed: %s", e)


def _emit_fallback(user_prompt: str, reason: str, detail: str) -> None:
    """Единый fallback-путь: логируем причину и печатаем исходный промпт."""
    logging.warning("Semantic search fallback (%s): %s", reason, detail)
    print(user_prompt)


def execute_semantic_search(user_prompt: str, trigger_found: str) -> None:
    """Execute semantic search and print results.
    The hook itself never raises – every path falls back to printing
    the original user_prompt so Claude Code stays unblocked.
    """
    try:
        l4_script = safe_path(CONFIG['l4_script'])
    except ValueError as exc:
        _emit_fallback(user_prompt, "unsafe_path", str(exc))
        return

    if not l4_script.exists():
        _emit_fallback(user_prompt, "not_found", f"L4 script not found: {l4_script}")
        return
    if not os.access(l4_script, os.R_OK):
        _emit_fallback(user_prompt, "no_access", f"No read access to L4 script: {l4_script}")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(l4_script), "search-all", user_prompt],
            capture_output=True,
            text=True,
            encoding=CONFIG['encoding'],
            check=False,
            timeout=SEMANTIC_SEARCH_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        _emit_fallback(
            user_prompt,
            "timeout",
            (
                f"L4 search exceeded "
                f"{SEMANTIC_SEARCH_TIMEOUT_SECONDS}s "
                f"budget for trigger '{trigger_found}'"
            ),
        )
        return
    except FileNotFoundError:
        _emit_fallback(user_prompt, "not_found", f"L4 script not found: {l4_script}")
        return
    except PermissionError:
        _emit_fallback(user_prompt, "no_access", f"No read access to L4 script: {l4_script}")
        return
    except subprocess.SubprocessError as exc:
        _emit_fallback(user_prompt, "subprocess_error", str(exc))
        return
    except OSError as exc:
        _emit_fallback(user_prompt, "os_error", str(exc))
        return
    except Exception as exc:
        _emit_fallback(user_prompt, "unexpected", str(exc))
        return

    # Проверяем код возврата – если скрипт упал, это тоже ошибка
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or f"L4 search returned non-zero exit code: {result.returncode}"
        )
        _emit_fallback(user_prompt, "subprocess_error", detail)
        return

    # Отслеживаем стоимость операции
    track_search_cost(user_prompt, result.stdout, trigger_found)

    if "[SEARCH ALL]" in result.stdout:
        print(user_prompt)
        print()
        print("<semantic_context>")
        print(result.stdout)
        print("</semantic_context>")
    else:
        print(user_prompt)


def main():
    """Main entry point"""
    user_prompt = read_user_prompt()
    should_run, trigger_found = should_search(user_prompt)
    if not should_run:
        print(user_prompt)
        return 0
    log_trigger(user_prompt, trigger_found)
    execute_semantic_search(user_prompt, trigger_found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
