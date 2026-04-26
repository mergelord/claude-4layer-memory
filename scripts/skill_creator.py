#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Creation Pipeline
Автоматическое создание навыков из успешных паттернов работы

Вдохновлено Hermes Agent closed learning loop
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import Counter
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


class SkillCreator:
    """Анализирует паттерны и создаёт навыки"""

    DEFAULT_MIN_PATTERN_COUNT = 3
    DEFAULT_MIN_SUCCESS_RATE = 0.8

    def __init__(
        self,
        min_pattern_count: int = DEFAULT_MIN_PATTERN_COUNT,
        min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
    ):
        self.claude_dir = Path.home() / ".claude"
        self.skills_dir = self.claude_dir / "skills"
        self.projects_dir = self.claude_dir / "projects"
        self.patterns_db = self.claude_dir / "skill_patterns.json"

        # Минимальные пороги для создания skill (можно переопределить через __init__)
        self.min_pattern_count = min_pattern_count
        self.min_success_rate = min_success_rate

    def safe_file_path(self, path: Path) -> Path:
        """Validate that path is within allowed directories"""
        try:
            resolved = path.resolve()
            # Check if path is within claude_dir
            if not str(resolved).startswith(str(self.claude_dir.resolve())):
                raise ValueError(f"Path outside allowed directory: {path}")
            return resolved
        except Exception as exc:
            raise ValueError(f"Invalid path: {path}") from exc

    def _extract_user_task(self, entry: Dict[str, Any]) -> str:
        """Extract task description from user message entry"""
        message = entry.get('message', {})
        content = message.get('content', '')

        if isinstance(content, str):
            return content[:100] if content else 'unknown'
        return 'unknown'

    def _extract_tool_calls(self, entry: Dict[str, Any]) -> List[str]:
        """Extract tool names from assistant message entry"""
        tools = []
        message = entry.get('message', {})
        content = message.get('content', [])

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    tool_name = block.get('name', '')
                    if tool_name:
                        tools.append(tool_name)
        return tools

    def _is_error_result(self, entry: Dict[str, Any]) -> bool:
        """Check if tool result indicates an error"""
        message = entry.get('message', {})
        return message.get('is_error', False)

    def _process_session_line(
        self,
        line: str,
        current_task: str,
        tool_sequence: List[str],
        patterns: List[Dict[str, Any]]
    ) -> tuple[str, List[str]]:
        """Process a single line from session file

        Returns:
            (updated_task, updated_tool_sequence)
        """
        try:
            entry = json.loads(line.strip())
            entry_type = entry.get('type')

            # Определяем начало задачи из user message
            if entry_type == 'user':
                if current_task and tool_sequence:
                    # Сохраняем предыдущий паттерн
                    patterns.append({
                        'task': current_task,
                        'tools': tool_sequence.copy(),
                        'success': True
                    })

                current_task = self._extract_user_task(entry)
                tool_sequence = []

            # Собираем последовательность tool calls
            elif entry_type == 'assistant':
                tools = self._extract_tool_calls(entry)
                tool_sequence.extend(tools)

            # Проверяем на ошибки в tool results
            elif entry_type == 'tool-result':
                if self._is_error_result(entry) and patterns:
                    patterns[-1]['success'] = False

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"Warning: Failed to process line: {e}", file=sys.stderr)

        return current_task, tool_sequence

    def analyze_session(self, session_file: Path) -> List[Dict[str, Any]]:
        """Анализирует сессию и извлекает паттерны"""
        if not session_file.exists():
            return []

        # Check read access
        if not os.access(session_file, os.R_OK):
            print(f"[WARN] No read access: {session_file}", file=sys.stderr)
            return []

        patterns: List[Dict[str, Any]] = []
        tool_sequence: List[str] = []
        current_task = None

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    current_task, tool_sequence = self._process_session_line(
                        line, current_task, tool_sequence, patterns
                    )

                # Сохраняем последний паттерн
                if current_task and tool_sequence:
                    patterns.append({
                        'task': current_task,
                        'tools': tool_sequence,
                        'success': True
                    })

        except Exception as e:
            print(f"[ERROR] Failed to analyze {session_file}: {e}", file=sys.stderr)

        return patterns

    @lru_cache(maxsize=1)
    def load_patterns_db(self) -> Dict[str, Any]:
        """Загружает базу паттернов (cached)"""
        if not self.patterns_db.exists():
            return {'patterns': {}, 'last_update': None}

        # Check read access
        if not os.access(self.patterns_db, os.R_OK):
            print(f"[WARN] No read access: {self.patterns_db}", file=sys.stderr)
            return {'patterns': {}, 'last_update': None}

        try:
            with open(self.patterns_db, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'patterns': {}, 'last_update': None}

    def save_patterns_db(self, db: Dict[str, Any]):
        """Сохраняет базу паттернов"""
        db['last_update'] = datetime.now().isoformat()
        # Clear cache after save
        self.load_patterns_db.cache_clear()
        try:
            with open(self.patterns_db, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] Failed to save patterns DB: {e}", file=sys.stderr)

    def update_patterns(self, new_patterns: List[Dict[str, Any]]):
        """Обновляет базу паттернов новыми данными"""
        db = self.load_patterns_db()

        for pattern in new_patterns:
            # Создаём ключ из последовательности инструментов
            tool_seq = tuple(pattern['tools'])
            key = str(tool_seq)

            if key not in db['patterns']:
                db['patterns'][key] = {
                    'tools': pattern['tools'],
                    'count': 0,
                    'success_count': 0,
                    'example_tasks': []
                }

            db['patterns'][key]['count'] += 1
            if pattern['success']:
                db['patterns'][key]['success_count'] += 1

            # Сохраняем примеры задач (максимум 5)
            if len(db['patterns'][key]['example_tasks']) < 5:
                db['patterns'][key]['example_tasks'].append(pattern['task'])

        self.save_patterns_db(db)

    def find_skill_candidates(self) -> List[Dict[str, Any]]:
        """Находит паттерны, которые можно превратить в skills"""
        db = self.load_patterns_db()
        candidates = []

        for pattern in db['patterns'].values():
            count = pattern['count']
            success_count = pattern['success_count']

            if count < self.min_pattern_count:
                continue

            success_rate = success_count / count if count > 0 else 0
            if success_rate < self.min_success_rate:
                continue

            # Паттерн должен содержать минимум 2 инструмента
            if len(pattern['tools']) < 2:
                continue

            candidates.append({
                'tools': pattern['tools'],
                'count': count,
                'success_rate': success_rate,
                'example_tasks': pattern['example_tasks']
            })

        # Сортируем по частоте использования
        candidates.sort(key=lambda x: x['count'], reverse=True)
        return candidates

    def generate_skill(self, candidate: Dict[str, Any], skill_name: str) -> str:
        """Генерирует SKILL.md файл"""
        tools = candidate['tools']
        examples = candidate['example_tasks'][:3]

        tools_block = "\n".join(f"{i + 1}. {tool}" for i, tool in enumerate(tools))
        examples_block = "\n".join(f"- {task}" for task in examples)

        # pylint: disable=line-too-long
        skill_content = f"""---
name: {skill_name}
description: Auto-generated skill from successful pattern (used {candidate['count']} times, {candidate['success_rate']:.0%} success rate)
---

# {skill_name}

**Auto-generated skill** based on observed successful patterns.

## Pattern

This skill automates the following tool sequence:
{tools_block}

## Example Tasks

This pattern was successfully used for:
{examples_block}

## Usage

```
/{skill_name.lower().replace(' ', '-')}
```

## Statistics

- Used: {candidate['count']} times
- Success rate: {candidate['success_rate']:.0%}
- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

**Note:** This is an auto-generated skill. Review and customize as needed.
"""
        return skill_content

    def create_skill_file(self, skill_name: str, content: str) -> bool:
        """Создаёт файл skill"""
        # Sanitize skill name
        safe_name = skill_name.lower().replace(' ', '-')
        # Remove potentially dangerous characters
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '-_')

        skill_dir = self.skills_dir / safe_name

        # Validate path
        try:
            self.safe_file_path(skill_dir)
        except ValueError as e:
            print(f"[ERROR] Invalid skill path: {e}", file=sys.stderr)
            return False

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        try:
            with open(skill_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] Created skill: {skill_file}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create skill: {e}", file=sys.stderr)
            return False

    def analyze_all_sessions(self, max_workers: int = 4) -> int:
        """Анализирует все сессии и обновляет паттерны (parallel)"""
        if not self.projects_dir.exists():
            return 0

        # Collect all session files
        session_files: List[Path] = []
        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            session_files.extend(project_dir.glob("*.jsonl"))

        if not session_files:
            return 0

        # Analyze in parallel
        all_patterns = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(self.analyze_session, f): f for f in session_files}
            for future in as_completed(future_to_file):
                try:
                    patterns = future.result()
                    if patterns:
                        all_patterns.extend(patterns)
                except Exception as exc:
                    file = future_to_file[future]
                    print(f"[WARN] Failed to analyze {file}: {exc}", file=sys.stderr)

        # Update patterns in batch
        if all_patterns:
            self.update_patterns(all_patterns)

        return len(session_files)

    def suggest_skills(self) -> List[Dict[str, Any]]:
        """Предлагает skills на основе паттернов"""
        candidates = self.find_skill_candidates()

        suggestions = []
        for candidate in candidates[:5]:  # Топ-5
            # Генерируем имя на основе инструментов
            tool_names = [t.replace('_', ' ').title() for t in candidate['tools'][:2]]
            skill_name = f"Auto {' + '.join(tool_names)}"

            suggestions.append({
                'name': skill_name,
                'candidate': candidate
            })

        return suggestions


def cmd_analyze(creator: SkillCreator):
    """Анализирует все сессии"""
    print("[INFO] Analyzing sessions...")
    count = creator.analyze_all_sessions()
    print(f"[OK] Analyzed {count} sessions")


def cmd_suggest(creator: SkillCreator):
    """Предлагает новые skills"""
    suggestions = creator.suggest_skills()

    if not suggestions:
        print("[INFO] No skill candidates found")
        print("       Patterns need to be used at least 3 times with 80% success rate")
        return

    print(f"\n[SUGGESTIONS] Found {len(suggestions)} skill candidates:\n")

    for i, suggestion in enumerate(suggestions, 1):
        candidate = suggestion['candidate']
        print(f"[{i}] {suggestion['name']}")
        print(f"    Tools: {' → '.join(candidate['tools'])}")
        print(f"    Used: {candidate['count']} times ({candidate['success_rate']:.0%} success)")
        print("    Examples:")
        for task in candidate['example_tasks'][:2]:
            print(f"      - {task}")
        print()


def cmd_create(creator: SkillCreator, skill_index: int):
    """Создаёт skill из предложения"""
    suggestions = creator.suggest_skills()

    if not suggestions:
        print("[ERROR] No skill candidates available")
        sys.exit(1)

    if skill_index < 1 or skill_index > len(suggestions):
        print(f"[ERROR] Invalid index. Choose 1-{len(suggestions)}")
        sys.exit(1)

    suggestion = suggestions[skill_index - 1]
    content = creator.generate_skill(suggestion['candidate'], suggestion['name'])

    if creator.create_skill_file(suggestion['name'], content):
        print(f"[OK] Skill created: {suggestion['name']}")
    else:
        print("[ERROR] Failed to create skill")
        sys.exit(1)


def cmd_stats(creator: SkillCreator):
    """Показывает статистику паттернов"""
    db = creator.load_patterns_db()
    patterns = db.get('patterns', {})

    if not patterns:
        print("[INFO] No patterns collected yet")
        print("       Run 'analyze' first")
        return

    total_patterns = len(patterns)
    total_uses = sum(p['count'] for p in patterns.values())

    # Топ-5 инструментов
    tool_counter: Counter = Counter()
    for pattern in patterns.values():
        tool_counter.update(pattern['tools'])

    print("\n[STATISTICS]")
    print(f"Total patterns: {total_patterns}")
    print(f"Total uses: {total_uses}")
    print(f"Last update: {db.get('last_update', 'Never')}")
    print("\nTop 5 tools:")
    for tool, count in tool_counter.most_common(5):
        print(f"  {tool}: {count} uses")


def main():
    """CLI интерфейс"""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCommands:")
        print("  analyze  - Analyze all sessions and update patterns")
        print("  suggest  - Show skill candidates")
        print("  create N - Create skill from suggestion #N")
        print("  stats    - Show pattern statistics")
        sys.exit(1)

    command = sys.argv[1]
    creator = SkillCreator()

    if command == 'analyze':
        cmd_analyze(creator)

    elif command == 'suggest':
        cmd_suggest(creator)

    elif command == 'create':
        if len(sys.argv) < 3:
            print("Usage: skill_creator.py create <index>")
            sys.exit(1)
        try:
            index = int(sys.argv[2])
            cmd_create(creator, index)
        except ValueError:
            print("[ERROR] Index must be a number")
            sys.exit(1)

    elif command == 'stats':
        cmd_stats(creator)

    else:
        print(f"[ERROR] Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
