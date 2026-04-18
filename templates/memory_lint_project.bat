@echo off
REM Memory Lint - Project Memory Check
REM Checks project-specific memory directory
REM Usage: memory_lint_project.bat [path] [--quick]
REM Example: memory_lint_project.bat . --quick

setlocal

set SCRIPT_DIR=%~dp0
set MEMORY_LINT=%USERPROFILE%\.claude\hooks\memory_lint.py

REM Default to current directory if no path provided
if "%~1"=="" (
    set MEMORY_PATH=.
) else (
    set MEMORY_PATH=%~1
)

echo.
echo ========================================
echo Memory Lint - Project Check
echo ========================================
echo.
echo Memory path: %MEMORY_PATH%
echo.

python "%MEMORY_LINT%" "%MEMORY_PATH%" %2 %3 %4

endlocal
