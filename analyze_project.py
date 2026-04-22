#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Architecture Analysis для Claude 4-Layer Memory System
Анализирует структуру проекта, зависимости, метрики
"""

import sys
import codecs
from pathlib import Path
from collections import defaultdict

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def analyze_structure():
    """Анализ структуры проекта"""
    print("\n" + "="*70)
    print("ARCHITECTURE ANALYSIS - Claude 4-Layer Memory System")
    print("="*70)

    root = Path(".")

    # Подсчёт файлов
    py_files = list(root.rglob("*.py"))
    sh_files = list(root.rglob("*.sh"))
    md_files = list(root.rglob("*.md"))

    print(f"\n📊 Статистика файлов:")
    print(f"  Python:    {len(py_files)} файлов")
    print(f"  Shell:     {len(sh_files)} файлов")
    print(f"  Markdown:  {len(md_files)} файлов")

    # Анализ директорий
    print(f"\n📁 Структура директорий:")
    dirs = defaultdict(int)
    for f in py_files:
        parent = f.parent.name if f.parent != Path(".") else "root"
        dirs[parent] += 1

    for dirname, count in sorted(dirs.items()):
        print(f"  {dirname:20s} {count:3d} файлов")

    # Подсчёт строк кода
    total_lines = 0
    code_lines = 0

    for py_file in py_files:
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            total_lines += len(lines)
            code_lines += sum(1 for line in lines
                            if line.strip() and not line.strip().startswith('#'))
        except Exception:
            pass

    print(f"\n📏 Метрики кода:")
    print(f"  Всего строк:     {total_lines:,}")
    print(f"  Строк кода:      {code_lines:,}")
    print(f"  Комментариев:    {total_lines - code_lines:,}")

    # Анализ зависимостей
    print(f"\n📦 Зависимости:")
    imports = set()
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding='utf-8')
            for line in content.split('\n'):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    imports.add(line.strip().split()[1].split('.')[0])
        except Exception:
            pass

    stdlib = {'sys', 'os', 'pathlib', 'json', 're', 'datetime', 'logging',
              'argparse', 'subprocess', 'sqlite3', 'typing', 'collections',
              'contextlib', 'codecs'}

    external = sorted(imports - stdlib - {'__future__'})
    print(f"  Внешние пакеты: {len(external)}")
    for pkg in external[:10]:
        print(f"    - {pkg}")

    # Ключевые компоненты
    print(f"\n🔑 Ключевые компоненты:")
    components = {
        'Cost Tracking': 'scripts/cost_tracker.py',
        'MCP Server': 'mcp_server.py',
        'FTS5 Search': 'scripts/l4_fts5_search.py',
        'Semantic Search': 'scripts/l4_semantic_global.py',
        'Memory Lint': 'scripts/memory_lint.py',
        'Skill Creator': 'scripts/skill_creator.py'
    }

    for name, path in components.items():
        exists = "✅" if Path(path).exists() else "❌"
        print(f"  {exists} {name:20s} {path}")

    print("\n" + "="*70)
    print("✅ Анализ завершён")
    print("="*70 + "\n")

if __name__ == '__main__':
    analyze_structure()
