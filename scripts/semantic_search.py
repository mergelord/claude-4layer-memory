#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Search Hook для Claude Code
Проверяет триггерные слова и добавляет контекст из L4 SEMANTIC
"""

import sys
import os
import subprocess

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
            ["python", l4_script, "search-all", user_prompt],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False
        )

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
