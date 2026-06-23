#!/usr/bin/env python3
"""
PreCompact Hook - сохранение памяти в L4 SEMANTIC перед компактификацией.

Когда Claude Code компактифицирует контекст, вся информация из текущей сессии
может быть потеряна. Этот хук сохраняет HOT и WARM память в векторную БД
перед компактом, чтобы знания можно было найти через семантический поиск.
"""

import sys
from pathlib import Path

# Добавляем путь к хукам
sys.path.insert(0, str(Path(__file__).parent))

try:
    # Импортируем L4 SEMANTIC
    from l4_semantic_global import GlobalSemanticMemory
except ImportError:
    print("[WARN] L4 SEMANTIC not available, skipping flush", file=sys.stderr)
    sys.exit(0)


def get_current_project():
    """Определяет текущий проект из CWD"""
    cwd = Path.cwd()

    # Проверяем, есть ли CLAUDE.md
    if (cwd / "CLAUDE.md").exists():
        return cwd

    # Fallback на CWD
    return cwd


def flush_to_l4():
    """Сохраняет текущую память в L4 SEMANTIC перед компактом"""
    try:
        print("[FLUSH] Saving memory to L4 SEMANTIC before compact...", file=sys.stderr)

        # Инициализируем L4 SEMANTIC
        memory = GlobalSemanticMemory()

        # Индексируем глобальную память
        # Current l4_semantic_global.py exposes index_all(). Older deployed
        # builds exposed index_global_memory()/index_project(); keep a fallback
        # so this hook still works if the semantic module is rolled back.
        if hasattr(memory, "index_all"):
            print("[FLUSH] Indexing all memory...", file=sys.stderr)
            memory.index_all()
        else:
            print("[FLUSH] Indexing global memory...", file=sys.stderr)
            memory.index_global_memory()

        # Always index the current project, regardless of index_all availability
        project_path = get_current_project()
        if (project_path / "memory").exists():
            print(f"[FLUSH] Indexing project: {project_path.name}...", file=sys.stderr)
            memory.index_project(project_path)

        print("[FLUSH] Memory saved to L4 SEMANTIC successfully", file=sys.stderr)
        return 0

    except Exception as e:
        print(f"[ERROR] Failed to flush memory: {e}", file=sys.stderr)
        # Не блокируем компакт при ошибке
        return 0


def main():
    """Main entry point"""
    return flush_to_l4()


if __name__ == "__main__":
    sys.exit(main())
