@echo off
REM Memory Lint - Full Check (global memory)
REM Runs all Layer 1 and Layer 2 checks
REM Usage: memory_lint_full.bat

python "%USERPROFILE%\.claude\hooks\memory_lint.py" --layer all
