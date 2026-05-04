"""Repo-wide encoding gate scanner.

Walks one or more directories for source files (``*.py``, ``*.md``,
``*.txt``, ``*.yml``, ``*.yaml``, ``*.toml``, ``*.json``, ``*.ini``,
``*.cfg``) and runs ``EncodingGate.scan_file`` on each. Emits a
human-readable report on stderr and exits with a non-zero status if
any file is flagged.

This is the **regression gate** for cp1251-as-utf8 mojibake and
``U+FFFD`` replacement-character corruption in the repository
itself, as opposed to ``memory_lint --validate-encoding`` which
targets the runtime memory tree.

It is wired into both:

* ``.pre-commit-config.yaml`` as a local hook so contributors get
  fail-fast feedback before they push.
* ``.github/workflows/lint.yml`` as a CI job so even pushes that
  bypass the local hook get caught at PR review time.

Usage::

    python scripts/scan_repo_encoding.py
    python scripts/scan_repo_encoding.py path/to/file.md
    python scripts/scan_repo_encoding.py scripts/ docs/ --quiet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# Allow ``python scripts/scan_repo_encoding.py`` invocation without
# requiring the caller to set PYTHONPATH.
_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# pylint: disable=wrong-import-position,import-error
from memory_lint_helpers import EncodingGate  # noqa: E402
# pylint: enable=wrong-import-position,import-error


# Files / directories that are intentionally exempt from the scan.
# - ``.git`` and ``__pycache__`` are noise.
# - ``.venv`` / ``venv`` / ``node_modules`` are vendored dependencies
#   we don't own and shouldn't fail CI on.
# - ``semantic_db_global`` and ``memory`` are runtime data, not source.
# - ``.bak`` / ``.fixed`` are repair artefacts (not source).
EXCLUDE_DIRS = frozenset({
    '.git',
    '__pycache__',
    '.venv',
    'venv',
    'env',
    'node_modules',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    'semantic_db_global',
    'memory',
    'archive',
    'feedback',
    'plugins',
    '.idea',
    '.vscode',
    'dist',
    'build',
    '.tox',
})

EXCLUDE_SUFFIXES = frozenset({
    '.bak',
    '.fixed',
    '.pyc',
    '.pyo',
})

# Files that legitimately contain mojibake / U+FFFD as part of their
# content (test fixtures, documentation that quotes the gate's own
# output, etc). Paths are POSIX-style and relative to the repo root.
# Add new entries sparingly — the whole point of this gate is to be
# the last line of defence against accidental corruption.
EXCLUDE_FILES = frozenset({
    # Intentional test fixtures: real cp1251-as-utf8 mojibake samples
    # the EncodingGate test suite asserts the detector catches.
    'tests/test_memory_lint_helpers.py',
    # Hook-level EncodingGate runtime guard tests: also embed the
    # canonical cp1251-as-utf8 mojibake fragment as a fixture to verify
    # the hooks refuse to write it.
    'tests/test_hooks_encoding_gate.py',
    # Documentation that quotes EncodingGate's own report verbatim,
    # which by construction contains mojibake characters as examples.
    'deploy/INSTALL_WINDOWS.md',
})

# File extensions that we treat as text-source and want to gate on.
INCLUDE_SUFFIXES = frozenset({
    '.py',
    '.md',
    '.txt',
    '.yml',
    '.yaml',
    '.toml',
    '.json',
    '.ini',
    '.cfg',
    '.sh',
    '.bat',
    '.ps1',
})


def _is_excluded_file(path: Path, repo_root: Path) -> bool:
    """Return True if ``path`` is in the explicit allowlist."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return rel.as_posix() in EXCLUDE_FILES


def _relative_parts(path: Path, repo_root: Path) -> Tuple[str, ...]:
    """Return ``path``'s parts relative to ``repo_root`` when possible.

    ``EXCLUDE_DIRS`` is meant to filter out directories *inside* the
    repository (e.g. ``.git``, ``node_modules``, ``memory``). Matching
    against the absolute parts of ``path`` would silently exclude
    every file in the repo if the clone happened to live under a
    directory whose name collides with the exclusion list (e.g.
    ``/home/user/build/repo/``, ``/srv/dist/repo/``). Resolving the
    parts against ``repo_root`` first prevents that false-pass.
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        # ``path`` lives outside the repo (CLI passed an absolute path
        # to somewhere unrelated). Fall back to absolute parts so the
        # filter still has a chance to skip obvious exclusions like
        # ``__pycache__``; this is a best-effort rather than a
        # silent-pass.
        return path.parts
    return rel.parts


def _passes_filters(path: Path, repo_root: Path) -> bool:
    """Return True iff ``path`` survives every include/exclude filter.

    Centralising this lets the file-branch and recursive-branch of
    :func:`_iter_source_files` apply identical rules — explicitly
    passing a file on the CLI must not bypass exclusions that would
    otherwise apply during a directory walk.
    """
    # Skip excluded directories *inside the repo*. ``.git`` /
    # ``__pycache__`` / ``node_modules`` etc. should never be scanned
    # even if a single file inside them is passed on the CLI. Match
    # against the path *relative to ``repo_root``* so the scanner is
    # not defeated by clones living under a directory whose name
    # happens to be in ``EXCLUDE_DIRS`` (``/home/user/build/repo/``
    # is a valid checkout location and must scan correctly).
    if any(part in EXCLUDE_DIRS for part in _relative_parts(path, repo_root)):
        return False
    # Skip ``.bak_<timestamp>`` style suffixes (pattern: anything
    # starting with ``.bak`` or ``.fixed``).
    if any(part.startswith('.bak') or part.startswith('.fixed')
           for part in path.suffixes):
        return False
    suffix = path.suffix.lower()
    if suffix in EXCLUDE_SUFFIXES:
        return False
    if suffix not in INCLUDE_SUFFIXES:
        return False
    if _is_excluded_file(path, repo_root):
        return False
    return True


def _iter_source_files(root: Path, repo_root: Path) -> Iterable[Path]:
    """Yield every source file under ``root`` honouring exclusions."""
    if root.is_file():
        if _passes_filters(root, repo_root):
            yield root
        return
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if _passes_filters(path, repo_root):
            yield path


def _scan(
    roots: Sequence[Path], repo_root: Path
) -> Tuple[List[Tuple[Path, str]], int]:
    """Scan every source file under ``roots``.

    Args:
        roots: Files or directories to scan.
        repo_root: Repository root used to resolve relative paths
            against ``EXCLUDE_FILES``.

    Returns:
        Tuple of ``(issues, scanned_count)``. ``issues`` is a list of
        ``(path, reason)`` for every file flagged by ``EncodingGate``.
    """
    issues: List[Tuple[Path, str]] = []
    scanned = 0
    for root in roots:
        if not root.exists():
            print(f"warning: path does not exist: {root}", file=sys.stderr)
            continue
        for path in _iter_source_files(root, repo_root):
            scanned += 1
            issue = EncodingGate.scan_file(path)
            if issue is not None:
                issues.append((path, issue))
    return issues, scanned


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Walk the given paths for source files (.py / .md / .txt / "
            ".yml / .toml / etc.) and fail if any contain "
            "cp1251-as-utf8 mojibake or U+FFFD replacement characters."
        )
    )
    parser.add_argument(
        'paths',
        nargs='*',
        help=(
            'Files or directories to scan. Defaults to the repo root '
            '(parent of scripts/).'
        ),
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress the scanned-count summary on success.',
    )
    args = parser.parse_args(argv)

    repo_root = _SCRIPTS.parent
    if args.paths:
        roots = [Path(p).resolve() for p in args.paths]
    else:
        # Default: repo root (parent of scripts/).
        roots = [repo_root]

    issues, scanned = _scan(roots, repo_root)

    if issues:
        print(
            f"Encoding gate FAILED: {len(issues)} of {scanned} file(s) "
            f"contain encoding corruption.",
            file=sys.stderr,
        )
        for path, reason in issues:
            try:
                rel = path.relative_to(Path.cwd())
            except ValueError:
                rel = path
            print(f"  {rel}: {reason}", file=sys.stderr)
        print(
            "\nRun ``python scripts/memory_lint.py <file_dir> "
            "--repair-mojibake`` to preview a fix, or fix the file by "
            "hand if it contains U+FFFD (lossy corruption).",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"Encoding gate passed: {scanned} file(s) scanned, all clean.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
