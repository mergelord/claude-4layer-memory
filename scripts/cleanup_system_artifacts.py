#!/usr/bin/env python3
r"""
Cleanup System Artifacts

Удаляет артефакты системных папок из ~/.claude/projects/
Эти папки создаются Claude Code CLI когда запускается с админскими правами
из системных директорий (C:\WINDOWS\system32, C:\Program Files и т.д.)

Usage:
    python cleanup_system_artifacts.py [--dry-run]
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Set

# Blacklist системных папок (encoded paths)
SYSTEM_PATH_PATTERNS: Set[str] = {
    # Windows
    "C--WINDOWS-system32",
    "C-WINDOWS-system32",
    "C--WINDOWS",
    "C-WINDOWS",
    "C--Program Files",
    "C-Program Files",
    "C--Program Files (x86)",
    "C-Program Files (x86)",

    # Linux/macOS
    "-usr-bin",
    "-usr-sbin",
    "-bin",
    "-sbin",
    "-etc",
    "-opt",
    "-var",
}


def is_system_artifact(project_name: str) -> bool:
    """Проверяет является ли папка артефактом системной директории."""
    return project_name in SYSTEM_PATH_PATTERNS


def find_system_artifacts(projects_dir: Path) -> List[Path]:
    """Находит все артефакты системных папок."""
    artifacts = []

    if not projects_dir.exists():
        return artifacts

    for project_path in projects_dir.iterdir():
        if not project_path.is_dir():
            continue

        if is_system_artifact(project_path.name):
            artifacts.append(project_path)

    return artifacts


def cleanup_artifacts(artifacts: List[Path], dry_run: bool = False) -> None:
    """Удаляет артефакты."""
    if not artifacts:
        print("[OK] No system artifacts found")
        return

    print(f"[INFO] Found {len(artifacts)} system artifact(s):")
    for artifact in artifacts:
        print(f"  - {artifact.name}")

    if dry_run:
        print("\n[DRY RUN] Would delete these artifacts (use without --dry-run to delete)")
        return

    print("\n[ACTION] Deleting artifacts...")
    for artifact in artifacts:
        try:
            shutil.rmtree(artifact)
            print(f"  [OK] Deleted: {artifact.name}")
        except Exception as e:
            print(f"  [ERROR] Failed to delete {artifact.name}: {e}", file=sys.stderr)

    print("\n[OK] Cleanup completed")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cleanup system artifacts from ~/.claude/projects/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    args = parser.parse_args()

    # Путь к projects/
    claude_dir = Path.home() / ".claude"
    projects_dir = claude_dir / "projects"

    if not projects_dir.exists():
        print(f"[ERROR] Projects directory not found: {projects_dir}", file=sys.stderr)
        sys.exit(1)

    # Находим артефакты
    artifacts = find_system_artifacts(projects_dir)

    # Удаляем
    cleanup_artifacts(artifacts, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
