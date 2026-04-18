@echo off
REM Memory Lint - Check project memory
REM Usage: memory_lint_project.bat [project_path]

setlocal

if "%~1"=="" (
    echo Usage: memory_lint_project.bat [project_path]
    echo Example: memory_lint_project.bat C:\BAT\msfs_autoland
    exit /b 1
)

set PROJECT_PATH=%~1

REM Convert path to memory directory format
REM C:\BAT\msfs_autoland -> C--BAT-msfs_autoland
set MEMORY_NAME=%PROJECT_PATH::=-%
set MEMORY_NAME=%MEMORY_NAME:\=-%

set MEMORY_PATH=%USERPROFILE%\.claude\projects\%MEMORY_NAME%\memory

if not exist "%MEMORY_PATH%" (
    echo Error: Project memory not found: %MEMORY_PATH%
    exit /b 1
)

call "%~dp0memory_lint.bat" "%MEMORY_PATH%"

endlocal
