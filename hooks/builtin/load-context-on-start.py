#!/usr/bin/env python3
"""
Load Context on Start Hook

Automatically loads context on Claude startup from C:/Users/MYRIG/.claude/:
- MEMORY_SYSTEM_GUIDE.md - memory system architecture
- memory/MEMORY.md - global memory index
- memory/handoff.md - recent events (HOT)
- memory/decisions.md - important decisions (WARM)
- GLOBAL_PROJECTS.md - active projects list

Outputs brief summary for Claude.
"""

import sys
from pathlib import Path
from typing import Optional

# Импорт кэширования
try:
    from hook_cache import HookCache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


def read_file_safe(file_path: Path, max_lines: Optional[int] = None, tail_lines: Optional[int] = None) -> Optional[str]:
    """Безопасное чтение файла с обработкой проблемных символов."""
    try:
        if not file_path.exists():
            return None

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        if tail_lines:
            # Берём последние N строк
            content = ''.join(lines[-tail_lines:]).strip()
        elif max_lines:
            # Берём первые N строк
            result = lines[:max_lines]
            if len(lines) > max_lines:
                result.append(f"... (truncated, total lines: {len(lines)})\n")
            content = ''.join(result).strip()
        else:
            # Весь файл
            content = ''.join(lines).strip()

        # Возвращаем UTF-8 контент как есть
        return content

    except Exception as e:
        return f"[Error reading {file_path.name}: {e}]"


def safe_print(text: str) -> None:
    """Безопасный вывод с форсированием UTF-8."""
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def load_context() -> str:
    """Load context and return as string."""
    claude_dir = Path.home() / ".claude"
    memory_dir = claude_dir / "memory"

    output = []
    output.append("=" * 80)
    output.append("[CONTEXT] 4-Layer Memory System Loaded")
    output.append("=" * 80)

    # 1. Архитектура системы (первые 50 строк)
    guide_path = claude_dir / "MEMORY_SYSTEM_GUIDE.md"
    guide_content = read_file_safe(guide_path, max_lines=50)
    if guide_content:
        output.append("\n## [ARCH] Memory System Architecture")
        output.append(guide_content)

    # 2. Индекс глобальной памяти (весь файл, он короткий)
    memory_index_path = memory_dir / "MEMORY.md"
    memory_index = read_file_safe(memory_index_path)
    if memory_index:
        output.append("\n## [INDEX] Global Memory Index")
        output.append(memory_index)

    # 3. HOT: handoff.md (последние 20 строк)
    handoff_path = memory_dir / "handoff.md"
    handoff_content = read_file_safe(handoff_path, tail_lines=20)
    if handoff_content:
        output.append("\n## [HOT] Recent Events (Last 20 lines)")
        output.append(handoff_content)

    # 4. WARM: decisions.md (последние 30 строк)
    decisions_path = memory_dir / "decisions.md"
    decisions_content = read_file_safe(decisions_path, tail_lines=30)
    if decisions_content:
        output.append("\n## [WARM] Important Decisions (Last 30 lines)")
        output.append(decisions_content)

    # 5. Список проектов (весь файл)
    projects_path = claude_dir / "GLOBAL_PROJECTS.md"
    projects_content = read_file_safe(projects_path, max_lines=100)
    if projects_content:
        output.append("\n## [PROJECTS] Active Projects")
        output.append(projects_content)

    # 6. Health Check (только если есть алерты)
    import subprocess
    health_script = claude_dir / "scripts" / "health_memory_size.py"
    if health_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(health_script)],
                capture_output=True, text=True, timeout=30
            )
            # Показываем только если есть алерты (exit code 1)
            if result.returncode != 0:
                output.append("\n## [HEALTH] Memory System Alerts")
                output.append(result.stdout.strip())
        except Exception as e:
            output.append(f"\n[WARNING] Health check failed: {e}")

    output.append("\n" + "=" * 80)
    output.append("[OK] Context loaded from C:/Users/MYRIG/.claude/")
    output.append("=" * 80)

    return '\n'.join(output)


def main() -> None:
    """Main entry point."""
    try:
        if CACHE_AVAILABLE:
            cache = HookCache("load-context-on-start")
            result = cache.get_or_run(load_context)
            safe_print(result)
        else:
            result = load_context()
            safe_print(result)

    except Exception as e:
        print(f"[ERROR] load-context-on-start.py failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
