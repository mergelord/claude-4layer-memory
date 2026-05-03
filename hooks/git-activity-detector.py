#!/usr/bin/env python3
"""
Git Activity Detector - отслеживает git команды и записывает в память.

Триггеры:
- git init → "Проект инициализирован"
- git commit → "Коммит: <message>"
- git push → "Push в <remote>/<branch>"
- Создание/изменение .gitignore → "Настроена защита от случайных коммитов"
- git remote add → "Добавлен remote: <url>"

Записывает в:
- Проектную память (всегда)
- Глобальную память (если публичный репозиторий или важное событие)
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path


def get_cwd():
    """Получает текущую рабочую директорию."""
    return Path(os.getcwd())


def detect_project():
    """Определяет проект из CWD."""
    # Blacklist системных папок
    SYSTEM_BLACKLIST = [
        'system32', 'System32', 'SYSTEM32',
        'Windows', 'WINDOWS', 'windows',
        'Program Files', 'Program Files (x86)',
        'ProgramData', 'AppData'
    ]

    cwd = get_cwd()

    # Проверка на системные папки
    if any(blacklisted in str(cwd) for blacklisted in SYSTEM_BLACKLIST):
        return None  # Игнорируем системные папки

    # Ищем ближайший .git или используем CWD
    current = cwd
    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent

    return cwd


def get_memory_paths(project_path):
    """Возвращает пути к памяти проекта."""
    # Кодируем путь проекта
    encoded = str(project_path).replace(':', '-').replace('\\', '-').replace('/', '-')
    base = Path.home() / ".claude" / "projects" / encoded / "memory"

    return {
        'handoff': base / "handoff.md",
        'decisions': base / "decisions.md",
        'memory_dir': base,
        'activity_log': Path.home() / ".claude" / "activity.log"
    }


def get_global_memory_paths():
    """Возвращает пути к глобальной памяти."""
    base = Path.home() / ".claude" / "memory"
    return {
        'handoff': base / "handoff.md",
        'decisions': base / "decisions.md",
        'memory_dir': base
    }


def run_git_command(cmd, cwd=None):
    """Выполняет git команду и возвращает результат."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", 1


def detect_git_activity(project_path):
    """
    Определяет git активность в проекте.

    Возвращает dict с информацией о git активности.
    """
    activity = {
        'has_git': False,
        'has_remote': False,
        'remote_url': None,
        'is_public': False,
        'last_commit': None,
        'last_commit_message': None,
        'branch': None,
        'uncommitted_changes': False,
        'gitignore_exists': False
    }

    # Проверка наличия .git
    if not (project_path / '.git').exists():
        return activity

    activity['has_git'] = True

    # Текущая ветка
    branch, rc = run_git_command(['git', 'branch', '--show-current'], cwd=project_path)
    if rc == 0:
        activity['branch'] = branch

    # Remote
    remote_output, rc = run_git_command(['git', 'remote', '-v'], cwd=project_path)
    if rc == 0 and remote_output:
        activity['has_remote'] = True
        # Парсим URL
        lines = remote_output.split('\n')
        for line in lines:
            if 'origin' in line and '(push)' in line:
                parts = line.split()
                if len(parts) >= 2:
                    activity['remote_url'] = parts[1]
                    # Определяем публичность
                    if 'github.com' in parts[1] or 'gitlab.com' in parts[1]:
                        activity['is_public'] = True
                    break

    # Последний коммит
    commit_hash, rc = run_git_command(['git', 'rev-parse', 'HEAD'], cwd=project_path)
    if rc == 0:
        activity['last_commit'] = commit_hash[:7]

        # Сообщение коммита
        msg, rc = run_git_command(['git', 'log', '-1', '--pretty=%s'], cwd=project_path)
        if rc == 0:
            activity['last_commit_message'] = msg

    # Uncommitted changes
    status, rc = run_git_command(['git', 'status', '--porcelain'], cwd=project_path)
    if rc == 0 and status:
        activity['uncommitted_changes'] = True

    # .gitignore
    if (project_path / '.gitignore').exists():
        activity['gitignore_exists'] = True

    return activity


def parse_activity_log():
    """
    Парсит activity.log для определения последних git команд.

    Возвращает список git событий.
    """
    activity_log = Path.home() / ".claude" / "activity.log"
    if not activity_log.exists():
        return []

    events = []

    try:
        with open(activity_log, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Ищем Bash команды с git
                    if entry.get('tool') == 'Bash':
                        command = entry.get('input', {}).get('command', '')

                        # git init
                        if 'git init' in command:
                            events.append({
                                'type': 'init',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git commit
                        elif 'git commit' in command:
                            events.append({
                                'type': 'commit',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git push
                        elif 'git push' in command:
                            events.append({
                                'type': 'push',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git remote add
                        elif 'git remote add' in command:
                            events.append({
                                'type': 'remote_add',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                    # Ищем Write/Edit для .gitignore
                    elif entry.get('tool') in ['Write', 'Edit']:
                        file_path = entry.get('input', {}).get('file_path', '')
                        if '.gitignore' in file_path:
                            events.append({
                                'type': 'gitignore',
                                'file': file_path,
                                'timestamp': entry.get('timestamp')
                            })

                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"[ERROR] Failed to parse activity log: {e}", file=sys.stderr)

    return events


def generate_git_summary(project_path, git_activity, git_events):
    """Генерирует сводку git активности для памяти."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary_parts = []

    # Заголовок
    if git_events:
        event_types = [e['type'] for e in git_events]
        if 'init' in event_types:
            title = "Git репозиторий инициализирован"
        elif 'push' in event_types:
            title = "Push в удалённый репозиторий"
        elif 'commit' in event_types:
            title = "Создан git коммит"
        elif 'gitignore' in event_types:
            title = ".gitignore настроен"
        else:
            title = "Git активность"
    else:
        title = "Git статус проверен"

    summary_parts.append(f"## {now} - {title}\n")

    # Информация о проекте
    if git_activity['has_git']:
        summary_parts.append(f"**Проект:** {project_path.name}")

        if git_activity['branch']:
            summary_parts.append(f"**Ветка:** {git_activity['branch']}")

        if git_activity['has_remote']:
            summary_parts.append(f"**Remote:** {git_activity['remote_url']}")
            if git_activity['is_public']:
                summary_parts.append("**Статус:** ✅ Публичный репозиторий")
            else:
                summary_parts.append("**Статус:** 🔒 Приватный репозиторий")
        else:
            summary_parts.append("**Remote:** Нет (локальный репозиторий)")

        if git_activity['last_commit']:
            summary_parts.append(f"**Последний коммит:** {git_activity['last_commit']}")
            if git_activity['last_commit_message']:
                summary_parts.append(f"**Сообщение:** {git_activity['last_commit_message']}")

        if git_activity['gitignore_exists']:
            summary_parts.append("**Защита:** .gitignore настроен")

    # События
    if git_events:
        summary_parts.append("\n**События:**")
        for event in git_events[-5:]:  # Последние 5
            if event['type'] == 'init':
                summary_parts.append("- Инициализирован git репозиторий")
            elif event['type'] == 'commit':
                summary_parts.append("- Создан коммит")
            elif event['type'] == 'push':
                summary_parts.append("- Push в удалённый репозиторий")
            elif event['type'] == 'remote_add':
                summary_parts.append("- Добавлен remote")
            elif event['type'] == 'gitignore':
                summary_parts.append("- Обновлён .gitignore")

    summary_parts.append("\n---\n")

    return "\n".join(summary_parts)


def is_global_worthy(git_activity, git_events):
    if not git_events:
        return False
    important=['init','push','remote_add','commit']
    return any(e['type'] in important for e in git_events)


def update_memory(memory_file: Path, new_entry: str):
    """Обновляет файл памяти."""
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    if not memory_file.exists():
        # Создаём новый файл
        header = """# HOT Memory - Handoff

Последние события и контекст проекта (окно 24 часа).

**Последнее обновление:** {now}

---

""".format(now=datetime.now().strftime("%Y-%m-%d %H:%M"))
        content = header + new_entry
    else:
        # Читаем существующий
        content = memory_file.read_text(encoding='utf-8')

        # Обновляем timestamp
        if '**Последнее обновление:**' in content:
            parts = content.split('**Последнее обновление:**')
            before = parts[0]
            after = parts[1].split('\n', 1)
            content = before + f"**Последнее обновление:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + after[1]

        # Добавляем новую запись после разделителя
        if '---' in content:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                content = parts[0] + '---' + parts[1] + '---\n\n' + new_entry + parts[2]
            else:
                content += '\n' + new_entry
        else:
            content += '\n' + new_entry

    memory_file.write_text(content, encoding='utf-8')


def main():
    """Main entry point."""
    try:
        # Определяем проект
        project_path = detect_project()

        # Check for system directories (blacklist)
        if project_path is None:
            return 0

        # Получаем пути к памяти
        project_memory = get_memory_paths(project_path)
        global_memory = get_global_memory_paths()

        # Определяем git активность
        git_activity = detect_git_activity(project_path)

        # Парсим activity log для git событий
        git_events = parse_activity_log()

                # Если нет git событий (commit/push/init/remote_add) - выходим
        # Проверяем только git_events, НЕ has_git
        # Иначе каждая сессия пишет "Git статус проверен" даже без действий
        if not git_events:
            return 0
         
        # Генерируем сводку
        summary = generate_git_summary(project_path, git_activity, git_events)

        # Записываем в проектную память
        update_memory(project_memory['handoff'], summary)
        print("[OK] Git activity recorded to project memory", file=sys.stderr)

        # Проверяем, нужно ли записывать в глобальную память
        if is_global_worthy(git_activity, git_events):
            update_memory(global_memory['handoff'], summary)
            print("[GLOBAL] Git activity recorded to global memory", file=sys.stderr)

        return 0

    except Exception as e:
        print(f"[ERROR] Git activity detector failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
