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
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Конфигурация
CONFIG: Dict[str, Any] = {
    'log_file': os.path.expanduser("~/.claude/hooks/semantic_search.log"),
    'l4_script': os.path.expanduser("~/.claude/hooks/l4_semantic_global.py"),
    'encoding': 'utf-8',
    'max_prompt_log_length': 100
}

# Триггерные фразы и паттерны
TRIGGERS = [
    # Русские фразы
    "как мы", "почему мы", "раньше", "помнишь", "что мы решили",
    "какое решение", "история", "в прошлый раз", "что мы",
    # Английские фразы
    "how did we", "why did we", "previously", "last time",
    "remember", "what did we decide", "history",
    # Лингвистические сигналы (из Claude Opus 4.7 промпта)
    # Притяжательные местоимения
    "my project", "my code", "my script", "my system", "my bug",
    "our project", "our code", "our system", "our approach",
    # Определенные артикли (контекстные)
    "the project", "the script", "the bug", "the issue", "the problem",
    "the solution", "the approach", "the system", "the code",
    # Прошедшее время (рекомендации/обсуждения)
    "you recommended", "you suggested", "you said", "you mentioned",
    "we discussed", "we decided", "we agreed", "we implemented",
    "you helped", "you fixed", "you created", "you wrote",
    # Русские эквиваленты
    "ты рекомендовал", "ты предложил", "ты говорил", "ты упоминал",
    "мы обсуждали", "мы решили", "мы согласились", "мы реализовали",
    "ты помог", "ты исправил", "ты создал", "ты написал"
]

def safe_path(path: str) -> Path:
    """Валидация пути - должен быть внутри home directory

    Args:
        path: Путь для проверки

    Returns:
        Path: Валидированный путь

    Raises:
        ValueError: Если путь выходит за пределы home directory
    """
    resolved = Path(path).resolve()
    home = Path.home().resolve()

    try:
        resolved.relative_to(home)
        return resolved
    except ValueError as exc:
        raise ValueError(f"Path {path} is outside home directory") from exc

def should_search(prompt: str) -> Tuple[bool, str]:
    """Проверяет, нужен ли семантический поиск

    Returns:
        (should_search, trigger_found): True если найден триггер, и сам триггер
    """
    prompt_lower = prompt.lower()
    for trigger in TRIGGERS:
        if trigger in prompt_lower:
            return True, trigger
    return False, ""

def read_user_prompt() -> str:
    """Read user prompt from stdin with proper encoding.

    On Windows the byte stream may be cp1251 (cmd.exe) or utf-8 (PowerShell).
    We must read the raw bytes ONCE and try several decoders against the
    same buffer; calling sys.stdin.buffer.read() a second time would return
    b'' because the stream is already consumed, silently dropping the prompt.
    """
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
        # latin-1 always succeeds for any byte sequence, but keep a final
        # safety net just in case future encodings are added/changed.
        return raw.decode('utf-8', errors='replace').strip()
    return sys.stdin.read().strip()


def log_trigger(user_prompt: str, trigger_found: str) -> None:
    """Log trigger activation to file"""
    try:
        log_file = safe_path(CONFIG['log_file'])
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Проверяем права на запись
        if log_file.exists() and not os.access(log_file, os.W_OK):
            logging.warning("No write access to log file: %s", log_file)
        else:
            with open(log_file, 'a', encoding=CONFIG['encoding']) as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                max_len = CONFIG['max_prompt_log_length']
                prompt_preview = user_prompt[:max_len] + "..." if len(user_prompt) > max_len else user_prompt
                f.write(f"[{timestamp}] Trigger: '{trigger_found}' | Prompt: {prompt_preview}\n")
    except (OSError, IOError, ValueError) as e:
        logging.debug("Logging failed: %s", e)


def track_search_cost(user_prompt: str, result_stdout: str, trigger_found: str) -> None:
    """Track cost of semantic search operation"""
    if not COST_TRACKING_ENABLED:
        return

    try:
        tracker = CostTracker()
        # Примерная оценка: prompt ~100 tokens, результат ~500 tokens
        input_tokens = len(user_prompt.split()) * 1.3  # ~1.3 tokens per word
        output_tokens = len(result_stdout.split()) * 1.3 if result_stdout else 0
        tracker.track_operation(
            operation_type='semantic_search',
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            model='embedding',
            metadata=f"trigger: {trigger_found}"
        )
    except Exception as e:  # nosec B110
        logging.debug("Cost tracking failed: %s", e)


def execute_semantic_search(user_prompt: str, trigger_found: str) -> None:
    """Execute semantic search and print results"""
    try:
        l4_script = safe_path(CONFIG['l4_script'])

        # Проверяем существование и права на выполнение
        if not l4_script.exists():
            raise FileNotFoundError(f"L4 script not found: {l4_script}")
        if not os.access(l4_script, os.R_OK):
            raise PermissionError(f"No read access to L4 script: {l4_script}")

        # Выполняем поиск
        result = subprocess.run(
            [sys.executable, str(l4_script), "search-all", user_prompt],
            capture_output=True,
            text=True,
            encoding=CONFIG['encoding'],
            check=False,
            timeout=30  # 30 секунд таймаут
        )

        # Отслеживаем стоимость операции
        track_search_cost(user_prompt, result.stdout, trigger_found)

        # Проверяем, есть ли результаты
        if "[SEARCH ALL]" in result.stdout:
            print(user_prompt)
            print()
            print("<semantic_context>")
            print(result.stdout)
            print("</semantic_context>")
        else:
            print(user_prompt)

    except Exception as e:
        # При ошибке просто возвращаем оригинальный prompt
        print(user_prompt, file=sys.stderr)
        print(f"[ERROR] Semantic search failed: {e}", file=sys.stderr)
        print(user_prompt)


def main():
    """Main entry point"""
    user_prompt = read_user_prompt()

    # Проверяем триггеры
    should_run, trigger_found = should_search(user_prompt)
    if not should_run:
        print(user_prompt)
        return 0

    # Логируем срабатывание триггера
    log_trigger(user_prompt, trigger_found)

    # Выполняем семантический поиск
    execute_semantic_search(user_prompt, trigger_found)

    return 0


if __name__ == "__main__":
    sys.exit(main())
