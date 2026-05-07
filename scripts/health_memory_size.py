#!/usr/bin/env python3
"""
Health check: memory layer sizes.

Exits with code 1 if any alert is triggered.
Designed for both CLI usage and CI integration.
"""

import sys
import io
from pathlib import Path
from typing import List, Optional

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
MEMORY_DIR = CLAUDE_DIR / "memory"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Пороги (можно вынести в конфиг позже)
MAX_HOT_ENTRIES = 20
MAX_MEMORY_MD_LINES = 200
MAX_CHROMADB_DOCS = 10_000

ALERTS: List[str] = []


def check_hot_layer() -> None:
    """Проверка глобального HOT слоя (HOT.md) на переполнение."""
    hot_file = MEMORY_DIR / "HOT.md"  # ✅ Правильный путь
    if not hot_file.exists():
        print("⏭️  Global HOT.md not found")
        return

    content = hot_file.read_text(encoding='utf-8')
    # Считаем записи по маркерам списка: "- [событие]"
    entries = [
        line for line in content.split('\n') if line.strip().startswith('- ')
    ]
    count = len(entries)

    if count > MAX_HOT_ENTRIES:
        ALERTS.append(
            f"Global HOT layer has {count} entries (threshold {MAX_HOT_ENTRIES})"
        )
        print(f"⚠️  Global HOT layer: {count} entries (limit {MAX_HOT_ENTRIES})")
    else:
        print(f"✅ Global HOT layer: {count} entries")


def check_project_hot_layers() -> None:
    """Проверка HOT слоёв в проектной памяти."""
    if not PROJECTS_DIR.exists():
        return

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        hot_file = project_dir / "memory" / "handoff.md"
        if not hot_file.exists():
            continue

        content = hot_file.read_text(encoding='utf-8')
        # В проектной памяти записи могут быть в формате ## дата
        entries = [
            line for line in content.split('\n') if line.startswith('## ')
        ]
        count = len(entries)

        if count > MAX_HOT_ENTRIES:
            ALERTS.append(
                f"Project {project_dir.name} HOT has {count} entries (threshold {MAX_HOT_ENTRIES})"
            )
            print(
                f"⚠️  Project {project_dir.name}: {count} HOT entries (limit {MAX_HOT_ENTRIES})"
            )
        else:
            print(f"✅ Project {project_dir.name}: {count} HOT entries")


def check_memory_md() -> None:
    """Проверка MEMORY.md на truncation risk."""
    memory_md = MEMORY_DIR / "MEMORY.md"
    if not memory_md.exists():
        print("⏭️  MEMORY.md not found")
        return

    lines = len(memory_md.read_text(encoding='utf-8').split('\n'))
    if lines > MAX_MEMORY_MD_LINES:
        ALERTS.append(
            f"MEMORY.md has {lines} lines (threshold {MAX_MEMORY_MD_LINES})"
        )
        print(f"⚠️  MEMORY.md: {lines} lines (limit {MAX_MEMORY_MD_LINES})")
    else:
        print(f"✅ MEMORY.md: {lines} lines")


def check_chromadb() -> None:
    """Проверка размера ChromaDB коллекций."""
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        print("⏭️  ChromaDB check skipped (not installed)")
        return

    # Поиск ChromaDB в стандартных путях
    db_path: Optional[Path] = None
    for candidate in [
        CLAUDE_DIR / "chroma_db",
        CLAUDE_DIR / "semantic_db_global",
    ]:
        if candidate.exists():
            db_path = candidate
            break

    if db_path is None:
        print("⏭️  ChromaDB not found")
        return

    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collections = client.list_collections()
    total_docs = 0
    for col in collections:
        count = col.count()
        total_docs += count
        print(f"   {col.name}: {count} docs")

    if total_docs > MAX_CHROMADB_DOCS:
        ALERTS.append(
            f"ChromaDB has {total_docs} total docs (threshold {MAX_CHROMADB_DOCS})"
        )
        print(f"⚠️  ChromaDB: {total_docs} total docs (limit {MAX_CHROMADB_DOCS})")
    else:
        print(f"✅ ChromaDB: {total_docs} total docs")


def main() -> int:
    print("🏥 Memory Health Check\n")

    # Check if Claude directory exists
    if not CLAUDE_DIR.exists():
        print(f"⏭️  Claude directory not found: {CLAUDE_DIR}")
        print("✅ Skipping health checks (not a Claude environment)")
        return 0

    check_hot_layer()
    check_project_hot_layers()
    check_memory_md()
    check_chromadb()

    if ALERTS:
        print(f"\n🚨 {len(ALERTS)} alert(s) triggered:")
        for alert in ALERTS:
            print(f"   - {alert}")
        return 1

    print("\n✅ All health checks passed")
    return 0


if __name__ == "__main__":
    # Fix Windows console encoding for emoji output (only when run directly)
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.exit(main())
