#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crash Recovery - Восстановление контекста из незавершённых сессий

Детектирует сессии которые завершились аварийно (без выполнения Stop hook)
и восстанавливает контекст из их транскриптов.

Запускается при SessionStart.
"""

import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Импорт кэширования
try:
    from hook_cache import HookCache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)


# Tags that look like system instructions to a future Claude reading handoff.md.
# Transcript user-entries are untrusted (they contain tool_result payloads from
# prior sessions), so any of these tags must be neutralized before write.
_INJECTION_TAG_RE = re.compile(
    r'</?(system-reminder|system|important|user)\b[^>]*>',
    re.IGNORECASE,
)


def _sanitize(text: str) -> str:
    """Neutralize injection-style tags found in untrusted transcript text."""
    if not text:
        return text
    return _INJECTION_TAG_RE.sub(
        lambda m: m.group(0).replace('<', '‹').replace('>', '›'),
        text,
    )


def _extract_user_text(content: Any) -> Optional[str]:
    """Pull genuine typed user text out of a transcript user-entry `content`.

    Returns None for tool_result payloads, structured non-text blocks, and
    non-string scalars — so raw tool output never reaches handoff.md.
    """
    if isinstance(content, str):
        collapsed = ' '.join(content.split())
        return collapsed or None
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'text':
                text = block.get('text', '')
                if isinstance(text, str) and text.strip():
                    parts.append(' '.join(text.split()))
        return ' '.join(parts) if parts else None
    return None


def _format_error(err: Any) -> str:
    """Summarize a transcript error entry as a short single-line string."""
    if isinstance(err, dict):
        status = err.get('status') or err.get('code')
        msg: Optional[str] = err.get('message')
        if not msg:
            cause = err.get('cause')
            if isinstance(cause, dict):
                msg = cause.get('code') or cause.get('message')
        if status and msg:
            out = f"{status}: {msg}"
        elif status:
            out = str(status)
        elif msg:
            out = str(msg)
        else:
            out = str(err)
    else:
        out = str(err)
    out = ' '.join(out.split())
    return out[:200]


class CrashRecovery:
    """Восстановление контекста из незавершённых сессий"""

    # Максимальный возраст сессии для восстановления (часы)
    MAX_SESSION_AGE_HOURS = 24

    # Минимальный размер транскрипта для восстановления (байты)
    MIN_TRANSCRIPT_SIZE = 1000

    def __init__(self):
        """Инициализация"""
        self.home = Path.home()
        self.claude_dir = self.home / ".claude"
        self.projects_base = self.claude_dir / "projects"

        # Файл для отслеживания обработанных сессий
        self.processed_sessions_file = self.claude_dir / ".crash_recovery_processed.json"
        self.processed_sessions = self._load_processed_sessions()

    def _load_processed_sessions(self) -> Set[str]:
        """Загрузить список уже обработанных сессий"""
        if not self.processed_sessions_file.exists():
            return set()

        try:
            with open(self.processed_sessions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('processed', []))
        except Exception as e:
            logging.warning("Failed to load processed sessions: %s", e)
            return set()

    def _save_processed_sessions(self):
        """Сохранить список обработанных сессий"""
        try:
            with open(self.processed_sessions_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processed': list(self.processed_sessions),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logging.error("Failed to save processed sessions: %s", e)

    def find_crashed_sessions(self) -> List[Dict]:
        """
        Найти незавершённые сессии

        Returns:
            Список словарей с информацией о сессиях
        """
        crashed = []
        cutoff_time = datetime.now() - timedelta(hours=self.MAX_SESSION_AGE_HOURS)

        if not self.projects_base.exists():
            return crashed

        # Ищем транскрипты во всех проектах
        for project_dir in self.projects_base.iterdir():
            if not project_dir.is_dir():
                continue

            # Ищем .jsonl файлы
            for transcript_file in project_dir.glob("*.jsonl"):
                # Пропускаем уже обработанные
                session_id = transcript_file.stem
                if session_id in self.processed_sessions:
                    continue

                # Проверяем возраст файла
                try:
                    mtime = datetime.fromtimestamp(transcript_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        continue

                    # Проверяем размер
                    size = transcript_file.stat().st_size
                    if size < self.MIN_TRANSCRIPT_SIZE:
                        continue

                    # Проверяем что сессия завершилась (файл не растёт)
                    # Если файл изменялся в последние 5 минут - сессия ещё активна
                    if (datetime.now() - mtime).total_seconds() < 300:
                        continue

                    crashed.append({
                        'session_id': session_id,
                        'transcript_path': transcript_file,
                        'project': project_dir.name,
                        'mtime': mtime,
                        'size': size
                    })

                except Exception as e:
                    logging.warning("Failed to check %s: %s", transcript_file.name, e)

        return crashed

    def extract_context_from_transcript(self, transcript_path: Path) -> Optional[Dict]:
        """
        Извлечь ключевой контекст из транскрипта

        Args:
            transcript_path: Путь к .jsonl файлу

        Returns:
            Словарь с контекстом или None
        """
        try:
            user_messages: List[str] = []
            tool_uses: List[str] = []
            errors: List[Any] = []

            with open(transcript_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # User messages — only genuine typed text, never tool_result payloads
                        if entry.get('type') == 'user':
                            text = _extract_user_text(
                                entry.get('message', {}).get('content', '')
                            )
                            if text and len(text) < 200:
                                user_messages.append(text)

                        # Tool uses
                        elif entry.get('type') == 'assistant':
                            message = entry.get('message', {})
                            content = message.get('content', [])
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'tool_use':
                                    tool_name = item.get('name', 'unknown')
                                    tool_uses.append(tool_name)

                        # Errors
                        if entry.get('error'):
                            errors.append(entry.get('error'))

                    except json.JSONDecodeError:
                        continue

            if not user_messages and not tool_uses:
                return None

            return {
                'user_messages': user_messages[-5:],  # Последние 5 сообщений
                'tool_uses': list(set(tool_uses)),  # Уникальные инструменты
                'errors': errors[-3:],  # Последние 3 ошибки
            }

        except Exception as e:
            logging.error("Failed to extract context from %s: %s", transcript_path.name, e)
            return None

    def recover_session(self, session_info: Dict) -> bool:
        """
        Восстановить контекст из сессии

        Args:
            session_info: Информация о сессии

        Returns:
            True если успешно
        """
        session_id = session_info['session_id']
        transcript_path = session_info['transcript_path']
        project = session_info['project']

        logging.info("Recovering session %s from project %s", session_id, project)

        # Извлекаем контекст
        context = self.extract_context_from_transcript(transcript_path)
        if not context:
            logging.warning("No context found in %s", session_id)
            return False

        # Формируем запись для handoff.md
        recovery_entry = self._format_recovery_entry(session_info, context)

        # Записываем в handoff.md проекта
        memory_path = self.projects_base / project / "memory"
        if not memory_path.exists():
            logging.warning("Memory path not found for %s", project)
            return False

        handoff_file = memory_path / "handoff.md"
        if not handoff_file.exists():
            logging.warning("handoff.md not found for %s", project)
            return False

        # Добавляем запись
        try:
            with open(handoff_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{recovery_entry}\n")

            logging.info("[OK] Recovered session %s", session_id)

            # Отмечаем как обработанную
            self.processed_sessions.add(session_id)
            self._save_processed_sessions()

            return True

        except Exception as e:
            logging.error("Failed to write recovery entry: %s", e)
            return False

    def _format_recovery_entry(self, session_info: Dict, context: Dict) -> str:
        """Форматировать запись для handoff.md"""
        session_id = session_info['session_id']
        mtime = session_info['mtime']

        entry = f"### [RECOVERED] {mtime.strftime('%Y-%m-%d %H:%M')}\n\n"
        entry += f"**Session ID:** `{session_id}`  \n"
        entry += "**Status:** Crashed (recovered automatically)  \n\n"

        if context.get('user_messages'):
            entry += "**User activity:**\n"
            for msg in context['user_messages']:
                entry += f"- {_sanitize(msg)}\n"
            entry += "\n"

        if context.get('tool_uses'):
            entry += "**Tools used:** "
            entry += ", ".join(context['tool_uses'][:10])
            entry += "\n\n"

        if context.get('errors'):
            entry += "**Errors:**\n"
            for err in context['errors']:
                entry += f"- {_sanitize(_format_error(err))}\n"
            entry += "\n"

        entry += "---\n"

        return entry

    def run(self) -> int:
        """
        Запустить восстановление

        Returns:
            Количество восстановленных сессий
        """
        crashed_sessions = self.find_crashed_sessions()

        if not crashed_sessions:
            logging.info("No crashed sessions found")
            return 0

        logging.info("Found %d crashed sessions", len(crashed_sessions))

        recovered_count = 0
        for session_info in crashed_sessions:
            if self.recover_session(session_info):
                recovered_count += 1

        return recovered_count


def main():
    """CLI интерфейс"""
    def run_recovery():
        recovery = CrashRecovery()
        recovered = recovery.run()

        if recovered > 0:
            return f"\n[CRASH RECOVERY] Restored {recovered} session(s)"
        return ""

    try:
        # Используем кэш если доступен
        if CACHE_AVAILABLE:
            cache = HookCache("crash-recovery")
            result = cache.get_or_run(run_recovery)
            if result:
                print(result)
        else:
            result = run_recovery()
            if result:
                print(result)

        sys.exit(0)

    except Exception as e:
        logging.error("Crash recovery failed: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
