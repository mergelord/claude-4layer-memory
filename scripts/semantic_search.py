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
from pathlib import Path

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

def should_search(prompt: str) -> tuple[bool, str]:
    """Проверяет, нужен ли семантический поиск

    Returns:
        (should_search, trigger_found): True если найден триггер, и сам триггер
    """
    prompt_lower = prompt.lower()
    for trigger in TRIGGERS:
        if trigger in prompt_lower:
            return True, trigger
    return False, ""

def main():
    # Читаем prompt из stdin с правильной кодировкой
    if sys.platform == 'win32':
        # Windows может передавать в cp1251 или utf-8
        try:
            user_prompt = sys.stdin.buffer.read().decode('utf-8').strip()
        except UnicodeDecodeError:
            try:
                user_prompt = sys.stdin.buffer.read().decode('cp1251').strip()
            except (UnicodeDecodeError, AttributeError):
                user_prompt = sys.stdin.read().strip()
    else:
        user_prompt = sys.stdin.read().strip()

    # Проверяем триггеры
    should_run, trigger_found = should_search(user_prompt)
    if not should_run:
        print(user_prompt)
        return 0

    # Логируем срабатывание триггера
    log_file = os.path.join(os.path.expanduser("~"), ".claude", "hooks", "semantic_search.log")
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] Trigger: '{trigger_found}' | Prompt: {user_prompt[:100]}...\n")
    except (OSError, IOError):
        pass  # Не критично если логирование не сработало

    # Выполняем семантический поиск
    l4_script = os.path.join(os.path.expanduser("~"), ".claude", "hooks", "l4_semantic_global.py")

    try:
        result = subprocess.run(
            [sys.executable, l4_script, "search-all", user_prompt],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False
        )

        # Отслеживаем стоимость операции
        if COST_TRACKING_ENABLED:
            try:
                tracker = CostTracker()
                # Примерная оценка: prompt ~100 tokens, результат ~500 tokens
                input_tokens = len(user_prompt.split()) * 1.3  # ~1.3 tokens per word
                output_tokens = len(result.stdout.split()) * 1.3 if result.stdout else 0
                tracker.track_operation(
                    operation_type='semantic_search',
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    model='embedding',
                    metadata=f"trigger: {trigger_found}"
                )
            except Exception as e:  # nosec B110
                logging.debug("Cost tracking failed: %s", e)

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

    return 0

if __name__ == "__main__":
    sys.exit(main())
