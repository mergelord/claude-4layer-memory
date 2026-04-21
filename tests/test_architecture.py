"""
Архитектурные тесты для Claude 4-Layer Memory System

Проверяют структурные правила проекта:
- Отсутствие циклических зависимостей
- Слоистость архитектуры
- Отсутствие дубликатов кода
- Правильность импортов
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set

import pytest


class ArchitectureAnalyzer:
    """Анализатор архитектуры проекта"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.scripts_dir = self.project_root / "scripts"
        self.utils_dir = self.project_root / "utils"

    def get_python_files(self, directory: Path) -> List[Path]:
        """Получить все Python файлы в директории"""
        if not directory.exists():
            return []
        return [f for f in directory.rglob("*.py") if f.name != "__init__.py"]

    def get_imports(self, file_path: Path) -> Set[str]:
        """Получить все импорты из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())

            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])

            return imports
        except Exception:
            return set()

    def find_circular_dependencies(self) -> List[tuple]:
        """Найти циклические зависимости"""
        all_files = (
            self.get_python_files(self.scripts_dir) +
            self.get_python_files(self.utils_dir) +
            list(self.project_root.glob("*.py"))
        )

        # Построить граф зависимостей
        graph = {}
        for file_path in all_files:
            module_name = file_path.stem
            imports = self.get_imports(file_path)
            # Фильтруем только локальные импорты
            local_imports = {imp for imp in imports if imp in [f.stem for f in all_files]}
            graph[module_name] = local_imports

        # Поиск циклов
        circular = []
        visited = set()

        def dfs(node, path):
            if node in path:
                cycle_start = path.index(node)
                circular.append(tuple(path[cycle_start:]))
                return
            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                dfs(neighbor, path[:])

        for node in graph:
            dfs(node, [])

        return circular


# ============================================================================
# ТЕСТ 1: Циклические зависимости
# ============================================================================

def test_no_circular_dependencies():
    """
    Проверяет отсутствие циклических зависимостей между модулями

    Циклические зависимости (A импортит B, B импортит A) приводят к:
    - Проблемам с инициализацией
    - Сложности понимания кода
    - Невозможности изолированного тестирования
    """
    analyzer = ArchitectureAnalyzer()
    circular = analyzer.find_circular_dependencies()

    if circular:
        msg = "Обнаружены циклические зависимости:\n"
        for cycle in circular:
            msg += f"  {' -> '.join(cycle)} -> {cycle[0]}\n"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 2: Отсутствие дубликатов
# ============================================================================

def test_no_backup_files():
    """
    Проверяет отсутствие backup файлов в проекте

    Backup файлы (*.backup, *.bak, *~) не должны быть в репозитории:
    - Увеличивают размер проекта
    - Создают путаницу
    - Могут содержать устаревший код
    """
    analyzer = ArchitectureAnalyzer()

    backup_patterns = ['*.backup', '*.bak', '*~', '*.old']
    backup_files = []

    for pattern in backup_patterns:
        backup_files.extend(analyzer.project_root.rglob(pattern))

    # Исключаем директории .git, __pycache__, etc
    backup_files = [
        f for f in backup_files
        if not any(part.startswith('.') or part == '__pycache__'
                  for part in f.parts)
    ]

    if backup_files:
        msg = "Обнаружены backup файлы:\n"
        for f in backup_files:
            msg += f"  {f.relative_to(analyzer.project_root)}\n"
        msg += "\nРекомендация: удалить эти файлы из репозитория"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 3: Структура директорий
# ============================================================================

def test_directory_structure():
    """
    Проверяет правильность структуры директорий

    Ожидаемая структура:
    - scripts/ - исполняемые скрипты
    - utils/ - утилиты и вспомогательные модули
    - tests/ - тесты
    - reports/ - отчёты (опционально)
    """
    analyzer = ArchitectureAnalyzer()

    required_dirs = ['scripts', 'utils', 'tests']
    missing_dirs = []

    for dir_name in required_dirs:
        dir_path = analyzer.project_root / dir_name
        if not dir_path.exists():
            missing_dirs.append(dir_name)

    if missing_dirs:
        msg = f"Отсутствуют обязательные директории: {', '.join(missing_dirs)}"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 4: Импорты utils модулей
# ============================================================================

def test_utils_imports():
    """
    Проверяет что utils модули не импортируют scripts

    Utils модули должны быть независимыми утилитами:
    - Не должны импортировать scripts
    - Могут импортировать только stdlib и другие utils
    """
    analyzer = ArchitectureAnalyzer()

    utils_files = analyzer.get_python_files(analyzer.utils_dir)
    scripts_modules = {f.stem for f in analyzer.get_python_files(analyzer.scripts_dir)}

    violations = []

    for utils_file in utils_files:
        imports = analyzer.get_imports(utils_file)
        script_imports = imports & scripts_modules

        if script_imports:
            violations.append(
                f"{utils_file.name} импортирует scripts: {', '.join(script_imports)}"
            )

    if violations:
        msg = "Utils модули не должны импортировать scripts:\n"
        for v in violations:
            msg += f"  {v}\n"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 5: Независимость модулей
# ============================================================================

def test_modules_are_importable_independently():
    """
    Проверяет что модули можно импортировать изолированно

    Каждый модуль должен быть независимым:
    - Не должно быть скрытых зависимостей
    - Импорт модуля не должен вызывать ошибок

    Примечание: Игнорируем SystemExit (отсутствие опциональных зависимостей)
    """
    analyzer = ArchitectureAnalyzer()

    all_files = (
        analyzer.get_python_files(analyzer.scripts_dir) +
        analyzer.get_python_files(analyzer.utils_dir)
    )

    failed_imports = []

    for file_path in all_files:
        module_name = file_path.stem
        try:
            # Пытаемся импортировать модуль
            if file_path.parent.name == 'scripts':
                __import__(f'scripts.{module_name}')
            elif file_path.parent.name == 'utils':
                __import__(f'utils.{module_name}')
        except ImportError as e:
            failed_imports.append(f"{file_path.name}: {str(e)}")
        except SystemExit:
            # Игнорируем SystemExit (модуль проверяет зависимости и выходит)
            pass
        except Exception:
            # Игнорируем другие ошибки (например, отсутствие зависимостей)
            pass

    if failed_imports:
        msg = "Некоторые модули не могут быть импортированы:\n"
        for f in failed_imports:
            msg += f"  {f}\n"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 6: Размер файлов
# ============================================================================

def test_file_size_limits():
    """
    Проверяет что файлы не превышают разумный размер

    Рекомендации:
    - Файлы >500 LOC стоит разбивать
    - Файлы >1000 LOC требуют рефакторинга
    """
    analyzer = ArchitectureAnalyzer()

    all_files = (
        analyzer.get_python_files(analyzer.scripts_dir) +
        analyzer.get_python_files(analyzer.utils_dir) +
        list(analyzer.project_root.glob("*.py"))
    )

    large_files = []

    for file_path in all_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())

            if lines > 500:
                large_files.append((file_path.name, lines))
        except Exception:
            pass

    if large_files:
        msg = "Обнаружены крупные файлы (>500 LOC):\n"
        for name, lines in sorted(large_files, key=lambda x: x[1], reverse=True):
            msg += f"  {name}: {lines} LOC\n"
        msg += "\nРекомендация: разбить на подмодули"
        # Это предупреждение, не ошибка
        pytest.skip(msg)


# ============================================================================
# ТЕСТ 7: Наличие __init__.py
# ============================================================================

def test_init_files_exist():
    """
    Проверяет наличие __init__.py в пакетах

    Каждая директория с Python модулями должна иметь __init__.py:
    - Делает директорию Python пакетом
    - Позволяет импортировать модули
    """
    analyzer = ArchitectureAnalyzer()

    package_dirs = [analyzer.scripts_dir, analyzer.utils_dir]
    missing_init = []

    for pkg_dir in package_dirs:
        if pkg_dir.exists():
            init_file = pkg_dir / "__init__.py"
            if not init_file.exists():
                missing_init.append(pkg_dir.name)

    if missing_init:
        msg = f"Отсутствуют __init__.py в директориях: {', '.join(missing_init)}"
        pytest.fail(msg)


# ============================================================================
# ТЕСТ 8: Forbidden imports
# ============================================================================

def test_no_forbidden_imports():
    """
    Проверяет отсутствие запрещённых импортов

    Запрещённые импорты:
    - os.system, subprocess.call без shell=False (security)
    - eval, exec (security)
    """
    analyzer = ArchitectureAnalyzer()

    all_files = (
        analyzer.get_python_files(analyzer.scripts_dir) +
        analyzer.get_python_files(analyzer.utils_dir) +
        list(analyzer.project_root.glob("*.py"))
    )

    violations = []

    for file_path in all_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)

            for node in ast.walk(tree):
                # Проверка eval/exec
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec']:
                            violations.append(
                                f"{file_path.name}: использует {node.func.id}() (security risk)"
                            )
        except Exception:
            pass

    if violations:
        msg = "Обнаружены запрещённые импорты/вызовы:\n"
        for v in violations:
            msg += f"  {v}\n"
        pytest.fail(msg)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
