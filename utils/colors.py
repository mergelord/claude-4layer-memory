"""ANSI color codes for terminal output"""
import os
import sys


def _supports_ansi() -> bool:
    """Detect whether the current terminal supports ANSI colour escapes.

    Non-Windows platforms are assumed to support ANSI.

    On Windows, classic cmd.exe / pre-v5 PowerShell don't support ANSI,
    but modern terminals (Windows Terminal, ConEmu, VS Code embedded
    terminal, mintty/git-bash) do. We check for well-known environment
    variables they expose; if none match, we fall back to the safe
    "disabled" behaviour.
    """
    if sys.platform != 'win32':
        return True

    indicator_env_vars = (
        'WT_SESSION',     # Windows Terminal (UUID, never 'OFF')
        'TERM_PROGRAM',   # VS Code, modern shells, mintty (program name)
        'ConEmuANSI',     # ConEmu — explicitly 'ON' or 'OFF'
        'ANSICON',        # ANSICON shim (version string)
    )
    # Don't just check presence: ConEmuANSI=OFF is a truthy string but
    # explicitly tells us the user disabled ANSI support, so we'd be
    # writing escape codes into a terminal that won't render them.
    # Treat empty / unset / 'OFF' as "no signal".
    return any(
        os.environ.get(var) not in (None, '', 'OFF')
        for var in indicator_env_vars
    )


class Colors:
    """ANSI color codes"""
    GREEN: str = '\033[92m'
    YELLOW: str = '\033[93m'
    RED: str = '\033[91m'
    BLUE: str = '\033[94m'
    CYAN: str = '\033[96m'
    BOLD: str = '\033[1m'
    END: str = '\033[0m'
    RESET: str = '\033[0m'  # alias for END

    @staticmethod
    def disable() -> None:
        """Disable colors for Windows or non-TTY environments"""
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.RED = ''
        Colors.BLUE = ''
        Colors.CYAN = ''
        Colors.BOLD = ''
        Colors.END = ''
        Colors.RESET = ''


if not _supports_ansi():
    Colors.disable()
