"""Tests for the EncodingGate runtime guard wired into hooks.

The Stop hook (``stop_handoff_universal.py``) and the git-activity
hook (``git-activity-detector.py``) collect text from sub-shells and
the user-facing activity log, then write that text into ``handoff.md``
or ``decisions.md``. A bad shell encoding (cp1251 console under
Windows, mis-decoded UTF-8 from older Git for Windows builds, etc.)
can leak cp1251-as-utf8 mojibake or U+FFFD replacement characters
into those values. The hooks are responsible for refusing to write
such corruption — the corresponding ``EncodingGate.assert_clean``
calls are tested here.

The hook source files use a hyphenated filename
(``git-activity-detector.py``) so they aren't importable as normal
Python modules; we load them through ``importlib.util.spec_from_file_location``
which is the canonical way to import a file without renaming it.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Ensure the hook modules can resolve their own ``memory_lint_helpers``
# import when the test process loads them.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_hook(hook_filename: str, module_alias: str) -> ModuleType:
    """Load a hook .py file as an importable module."""
    hook_path = HOOKS_DIR / hook_filename
    spec = importlib.util.spec_from_file_location(module_alias, hook_path)
    assert spec is not None and spec.loader is not None, (
        f"Cannot load hook {hook_path}"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def stop_hook() -> ModuleType:
    """Load ``hooks/stop_handoff_universal.py`` as a module."""
    return _load_hook("stop_handoff_universal.py", "stop_handoff_universal_under_test")


@pytest.fixture(scope="module")
def git_hook() -> ModuleType:
    """Load ``hooks/git-activity-detector.py`` as a module."""
    return _load_hook("git-activity-detector.py", "git_activity_detector_under_test")


# --- Stop hook: update_handoff -------------------------------------------------


def test_stop_hook_imports_encoding_gate(stop_hook: ModuleType) -> None:
    """Stop hook must successfully import EncodingGate from sibling scripts/."""
    assert stop_hook.EncodingGate is not None, (
        "EncodingGate import failed; runtime guard would be a no-op"
    )
    assert stop_hook.EncodingError is not None


def test_update_handoff_accepts_clean_cyrillic(
    stop_hook: ModuleType, tmp_path: Path
) -> None:
    """Clean Cyrillic text passes through ``update_handoff`` unchanged."""
    handoff = tmp_path / "handoff.md"
    summary = (
        "## 2025-01-15 12:34 - Session completed\n\n"
        "**Файлы:**\n- scripts/memory_lint.py\n\n---\n"
    )

    stop_hook.update_handoff(handoff, "demo-project", summary)

    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "## 2025-01-15 12:34 - Session completed" in content
    assert "scripts/memory_lint.py" in content


def test_update_handoff_rejects_replacement_char(
    stop_hook: ModuleType, tmp_path: Path
) -> None:
    """U+FFFD in the summary triggers EncodingError before disk write."""
    handoff = tmp_path / "handoff.md"
    poisoned = "## 2025-01-15 - Session completed\n\nbroken \ufffd byte\n---\n"

    with pytest.raises(stop_hook.EncodingError):
        stop_hook.update_handoff(handoff, "demo-project", poisoned)

    assert not handoff.exists(), (
        "EncodingGate must refuse before any disk write occurs"
    )


def test_update_handoff_rejects_cp1251_mojibake(
    stop_hook: ModuleType, tmp_path: Path
) -> None:
    """cp1251-as-utf8 mojibake in the summary triggers EncodingError."""
    handoff = tmp_path / "handoff.md"
    # Real-world fixture: "Рефакторинг 6 модулей" round-tripped
    # through latin-1.encode -> utf-8.decode (the canonical Windows
    # mojibake pattern from sub-shell output).
    poisoned_summary = (
        "## 2025-01-15 - Session completed\n\n"
        "Р\u00a0РµС„Р°РєС‚РѕСЂРёРЅРі 6 РјРѕРґСѓР»РµР№\n---\n"
    )

    with pytest.raises(stop_hook.EncodingError):
        stop_hook.update_handoff(handoff, "demo-project", poisoned_summary)

    assert not handoff.exists()


# --- git-activity-detector hook: update_memory --------------------------------


def test_git_hook_imports_encoding_gate(git_hook: ModuleType) -> None:
    """git-activity-detector must import EncodingGate successfully."""
    assert git_hook.EncodingGate is not None
    assert git_hook.EncodingError is not None


def test_update_memory_accepts_clean_entry(
    git_hook: ModuleType, tmp_path: Path
) -> None:
    """A clean Cyrillic git summary passes through ``update_memory``."""
    memory = tmp_path / "handoff.md"
    new_entry = (
        "## 2025-01-15 12:34 - Git: коммит\n\n"
        "**Branch:** main\n"
        "**Message:** Добавлена поддержка UTF-8\n\n---\n"
    )

    git_hook.update_memory(memory, new_entry)

    assert memory.exists()
    content = memory.read_text(encoding="utf-8")
    assert "Добавлена поддержка UTF-8" in content


def test_update_memory_rejects_replacement_char(
    git_hook: ModuleType, tmp_path: Path
) -> None:
    """U+FFFD in the new entry triggers EncodingError before disk write."""
    memory = tmp_path / "handoff.md"
    poisoned_entry = "## 2025-01-15 - Git\n\ncommit \ufffd msg\n---\n"

    with pytest.raises(git_hook.EncodingError):
        git_hook.update_memory(memory, poisoned_entry)

    assert not memory.exists()


def test_update_memory_rejects_cp1251_mojibake(
    git_hook: ModuleType, tmp_path: Path
) -> None:
    """cp1251-as-utf8 mojibake in a git entry triggers EncodingError."""
    memory = tmp_path / "handoff.md"
    poisoned_entry = (
        "## 2025-01-15 - Git\n\n"
        "Р\u00a0РµС„Р°РєС‚РѕСЂРёРЅРі 6 РјРѕРґСѓР»РµР№\n---\n"
    )

    with pytest.raises(git_hook.EncodingError):
        git_hook.update_memory(memory, poisoned_entry)

    assert not memory.exists()


def test_update_memory_preserves_existing_legacy_mojibake(
    git_hook: ModuleType, tmp_path: Path
) -> None:
    """Existing on-disk mojibake from pre-v1.3.2 hooks is left untouched.

    The runtime guard must check only the *new* entry. If the
    existing handoff.md contains legacy mojibake the user has not yet
    repaired (with ``memory_lint --repair-mojibake``), the hook still
    appends new clean entries on top of it instead of refusing to
    write forever.
    """
    memory = tmp_path / "handoff.md"
    # Seed disk with an existing file that already contains mojibake
    # — simulating a legacy handoff.md from a pre-v1.3.2 hook run.
    legacy_content = (
        "# HOT Memory - Handoff\n\n"
        "**Последнее обновление:** 2024-01-01 00:00\n\n"
        "---\n\n"
        "## 2024-01-01 - Old session\n\n"
        "Р\u00a0РµС„Р°РєС‚РѕСЂРёРЅРі (legacy mojibake)\n\n---\n"
    )
    memory.write_text(legacy_content, encoding="utf-8")

    clean_entry = (
        "## 2025-01-15 - Git: новый коммит\n\nКлючевая правка\n\n---\n"
    )
    git_hook.update_memory(memory, clean_entry)

    final = memory.read_text(encoding="utf-8")
    assert "Ключевая правка" in final
    # Legacy mojibake remains on disk: hook is non-destructive.
    assert "Р\u00a0РµС„Р°РєС‚РѕСЂРёРЅРі" in final
