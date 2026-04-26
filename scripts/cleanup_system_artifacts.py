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
import os
import shutil
import sys
from pathlib import Path
from typing import List, Set, Tuple

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


def normalize_path(path_str: str) -> str:
    """Normalize path for comparison (remove special chars)."""
    return path_str.replace('\\', '-').replace('/', '-').replace(':', '-')


def is_system_artifact(project_name: str) -> bool:
    """Проверяет является ли папка артефактом системной директории.

    All entries in SYSTEM_PATH_PATTERNS are stored in normalized form
    (slashes / backslashes / colons replaced by '-'), so we only need
    one membership check after normalizing the input.
    """
    return normalize_path(project_name) in SYSTEM_PATH_PATTERNS


def find_system_artifacts(projects_dir: Path) -> List[Path]:
    """Находит все артефакты системных папок."""
    artifacts: List[Path] = []

    if not projects_dir.exists():
        return artifacts

    # Check read access
    if not os.access(projects_dir, os.R_OK):
        print(f"[WARN] No read access: {projects_dir}", file=sys.stderr)
        return artifacts

    for project_path in projects_dir.iterdir():
        if not project_path.is_dir():
            continue

        if is_system_artifact(project_path.name):
            artifacts.append(project_path)

    return artifacts


def cleanup_artifacts(artifacts: List[Path], dry_run: bool = False,
                     verbose: bool = False, projects_dir: Path = None) -> Tuple[int, int]:
    """Удаляет артефакты. Returns (deleted_count, failed_count)."""
    if not artifacts:
        print("[OK] No system artifacts found")
        return (0, 0)

    print(f"[INFO] Found {len(artifacts)} system artifact(s):")
    for artifact in artifacts:
        print(f"  - {artifact.name}")

    if dry_run:
        print("\n[DRY RUN] Would delete these artifacts (use without --dry-run to delete)")
        return (0, 0)

    print("\n[ACTION] Deleting artifacts...")
    deleted_count = 0
    failed_count = 0

    for artifact in artifacts:
        try:
            # Validate path is within projects_dir
            if projects_dir:
                try:
                    artifact.resolve().relative_to(projects_dir.resolve())
                except ValueError:
                    print(f"  [ERROR] Path outside projects dir: {artifact.name}", file=sys.stderr)
                    failed_count += 1
                    continue

            # Check write access
            if not os.access(artifact, os.W_OK):
                print(f"  [ERROR] No write access: {artifact.name}", file=sys.stderr)
                failed_count += 1
                continue

            # Compute size BEFORE deletion (after rmtree the dir is gone)
            dir_size = _get_dir_size(artifact) if verbose else 0

            shutil.rmtree(artifact)
            print(f"  [OK] Deleted: {artifact.name}")
            deleted_count += 1

            if verbose:
                print(f"       Size freed: {dir_size} bytes")

        except Exception as e:
            print(f"  [ERROR] Failed to delete {artifact.name}: {e}", file=sys.stderr)
            failed_count += 1

    print(f"\n[STATS] Deleted: {deleted_count}, Failed: {failed_count}")
    print("[OK] Cleanup completed")
    return (deleted_count, failed_count)


def _get_dir_size(path: Path) -> int:
    """Calculate directory size (for verbose mode)."""
    try:
        total = 0
        for entry in path.rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
        return total
    except Exception:
        return 0


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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output"
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
    _deleted, failed = cleanup_artifacts(artifacts, dry_run=args.dry_run,
                                        verbose=args.verbose, projects_dir=projects_dir)

    # Exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
