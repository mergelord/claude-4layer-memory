@echo off
REM Memory Lint - Quick Check (global memory)
REM Checks only critical errors (ghost links)
REM Usage: memory_lint_quick.bat

python "%USERPROFILE%\.claude\hooks\memory_lint.py" --layer 1 --quick
