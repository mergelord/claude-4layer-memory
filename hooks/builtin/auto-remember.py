#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Remember Hook - Автоматическое сохранение фактов

Автоматически ловит фразы типа "запомни: X" и сохраняет в memory
без явного вызова Write tool.

Вдохновлено CliClaw (https://github.com/a-prs/CliClaw)

Запускается при UserPromptSubmit.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)


class AutoRemember:
    """Автоматическое сохранение фактов из user messages"""

    # Regex паттерны для обнаружения "запомни"
    REMEMBER_PATTERNS = [
        r"запомни[:\s]+(.+?)(?:\.|$)",
        r"remember[:\s]+(.+?)(?:\.|$)",
        r"сохрани[:\s]+(.+?)(?:\.|$)",
        r"save[:\s]+(.+?)(?:\.|$)",
        r"не забудь[:\s]+(.+?)(?:\.|$)",
        r"don't forget[:\s]+(.+?)(?:\.|$)",
    ]

    def __init__(self):
        """Инициализация"""
        self.home = Path.home()
        self.claude_dir = self.home / ".claude"
        self.projects_base = self.claude_dir / "projects"

    def extract_facts(self, text: str) -> List[str]:
        """
        Извлечь факты из текста

        Args:
            text: Текст user message

        Returns:
            Список извлечённых фактов
        """
        facts = []

        for pattern in self.REMEMBER_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                fact = match.group(1).strip()
                if fact and len(fact) > 3:  # Минимум 3 символа
                    facts.append(fact)

        return facts

    def save_fact(self, fact: str, project: str) -> bool:
        """
        Сохранить факт в memory

        Args:
            fact: Текст факта
            project: Имя проекта

        Returns:
            True если успешно
        """
        # Определяем куда сохранять
        memory_path = self.projects_base / project / "memory"

        if not memory_path.exists():
            logging.warning("Memory path not found for %s", project)
            return False

        # Сохраняем в decisions.md (WARM layer)
        decisions_file = memory_path / "decisions.md"

        if not decisions_file.exists():
            logging.warning("decisions.md not found for %s", project)
            return False

        try:
            now = datetime.now()
            entry = f"\n### [AUTO-REMEMBER] {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            entry += f"{fact}\n\n"
            entry += "---\n\n"

            with open(decisions_file, 'a', encoding='utf-8') as f:
                f.write(entry)

            logging.info("✓ Auto-saved fact: %s...", fact[:50])
            return True

        except Exception as e:
            logging.error("Failed to save fact: %s", e)
            return False

    def run(self, prompt: str, cwd: str) -> int:
        """
        Запустить auto-remember

        Args:
            prompt: User prompt
            cwd: Текущая рабочая директория

        Returns:
            Количество сохранённых фактов
        """
        # Извлекаем факты
        facts = self.extract_facts(prompt)

        if not facts:
            return 0

        # Определяем проект из CWD
        # Пытаемся найти соответствующую директорию в projects_base
        project = None

        # Простой подход: берём последний сегмент пути
        cwd_path = Path(cwd)
        for project_dir in self.projects_base.iterdir():
            if project_dir.is_dir():
                # Проверяем совпадение имени
                if cwd_path.name.lower() in project_dir.name.lower():
                    project = project_dir.name
                    break

        # Fallback: используем system32 проект
        if not project:
            project = "C--WINDOWS-system32"

        # Сохраняем факты
        saved_count = 0
        for fact in facts:
            if self.save_fact(fact, project):
                saved_count += 1

        if saved_count > 0:
            print(f"\n[AUTO-REMEMBER] Saved {saved_count} fact(s) to memory")

        return saved_count


def main():
    """CLI интерфейс"""
    # Получаем параметры из environment
    hook_data = os.environ.get('CLAUDE_HOOK_DATA')

    if not hook_data:
        # Fallback: читаем из stdin или argv
        if len(sys.argv) > 1:
            prompt = ' '.join(sys.argv[1:])
            cwd = os.getcwd()
        else:
            # Тихий выход если нет данных (нормальная ситуация)
            sys.exit(0)
    else:
        try:
            data = json.loads(hook_data)
            prompt = data.get('prompt', '')
            cwd = data.get('cwd', os.getcwd())
        except Exception as e:
            logging.error("Failed to parse hook data: %s", e)
            sys.exit(0)

    try:
        auto_remember = AutoRemember()
        auto_remember.run(prompt, cwd)
        sys.exit(0)

    except Exception as e:
        logging.error("Auto-remember failed: %s", e)
        sys.exit(0)  # Не блокируем работу при ошибке


if __name__ == '__main__':
    main()
