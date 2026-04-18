@echo off
REM Memory Lint - Windows wrapper
REM Validates memory structure and content

setlocal

set SCRIPT_DIR=%~dp0
set MEMORY_LINT=%SCRIPT_DIR%..\memory_lint.py

REM Default to global memory if no path provided
if "%~1"=="" (
    set MEMORY_PATH=%USERPROFILE%\.claude\memory
) else (
    set MEMORY_PATH=%~1
)

echo.
echo ========================================
echo Memory Lint System
echo ========================================
echo.
echo Memory path: %MEMORY_PATH%
echo.

python "%MEMORY_LINT%" "%MEMORY_PATH%" %2 %3 %4

endlocal
