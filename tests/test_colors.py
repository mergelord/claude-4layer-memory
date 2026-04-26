"""Tests for utils/colors.py — ANSI support detection and disable()."""
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `import utils.colors` works
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import colors as colors_mod  # noqa: E402  pylint: disable=wrong-import-position


def test_supports_ansi_on_posix(monkeypatch):
    """Non-Windows platforms must report ANSI as supported."""
    monkeypatch.setattr(colors_mod.sys, "platform", "linux")
    assert colors_mod._supports_ansi() is True  # pylint: disable=protected-access


def test_supports_ansi_on_windows_classic(monkeypatch):
    """Windows without modern-terminal env vars must report ANSI as unsupported."""
    monkeypatch.setattr(colors_mod.sys, "platform", "win32")
    for var in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"):
        monkeypatch.delenv(var, raising=False)
    assert colors_mod._supports_ansi() is False  # pylint: disable=protected-access


@pytest.mark.parametrize(
    "env_var",
    ["WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"],
)
def test_supports_ansi_on_windows_modern(monkeypatch, env_var):
    """Windows with a modern-terminal env var set must report ANSI as supported."""
    monkeypatch.setattr(colors_mod.sys, "platform", "win32")
    for var in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(env_var, "1")
    assert colors_mod._supports_ansi() is True  # pylint: disable=protected-access


def test_supports_ansi_conemu_off_treated_as_unsupported(monkeypatch):
    """ConEmuANSI='OFF' is a truthy string but explicitly disables ANSI.

    Regression for the presence-only check that returned True for any
    non-empty value: ``ConEmuANSI=OFF`` would have been treated as a
    positive signal, sending escape codes to a terminal where the user
    explicitly turned ANSI off.
    """
    monkeypatch.setattr(colors_mod.sys, "platform", "win32")
    for var in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ConEmuANSI", "OFF")
    assert colors_mod._supports_ansi() is False  # pylint: disable=protected-access


def test_supports_ansi_conemu_on_treated_as_supported(monkeypatch):
    """ConEmuANSI='ON' must enable ANSI."""
    monkeypatch.setattr(colors_mod.sys, "platform", "win32")
    for var in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ConEmuANSI", "ON")
    assert colors_mod._supports_ansi() is True  # pylint: disable=protected-access


def test_supports_ansi_empty_env_var_is_no_signal(monkeypatch):
    """An env var explicitly set to '' must not be treated as a positive signal."""
    monkeypatch.setattr(colors_mod.sys, "platform", "win32")
    for var in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI", "ANSICON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WT_SESSION", "")
    assert colors_mod._supports_ansi() is False  # pylint: disable=protected-access


def test_disable_clears_all_codes():
    """Colors.disable() must zero out every colour attribute."""
    saved = {
        attr: getattr(colors_mod.Colors, attr)
        for attr in ("GREEN", "YELLOW", "RED", "BLUE", "CYAN", "BOLD", "END", "RESET")
    }
    try:
        colors_mod.Colors.GREEN = "\033[92m"
        colors_mod.Colors.YELLOW = "\033[93m"
        colors_mod.Colors.RED = "\033[91m"
        colors_mod.Colors.BLUE = "\033[94m"
        colors_mod.Colors.CYAN = "\033[96m"
        colors_mod.Colors.BOLD = "\033[1m"
        colors_mod.Colors.END = "\033[0m"
        colors_mod.Colors.RESET = "\033[0m"

        colors_mod.Colors.disable()

        for attr in ("GREEN", "YELLOW", "RED", "BLUE", "CYAN", "BOLD", "END", "RESET"):
            assert getattr(colors_mod.Colors, attr) == "", f"{attr} should be empty after disable()"
    finally:
        # Restore original state so other tests aren't affected
        for attr, value in saved.items():
            setattr(colors_mod.Colors, attr, value)
