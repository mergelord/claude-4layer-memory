@echo off
REM Claude 4-Layer Memory System - Windows Installation Script
REM Copyright (c) 2026 Project Contributors
REM Licensed under MIT License

echo ========================================
echo Claude 4-Layer Memory System
echo Installation Script for Windows
echo ========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python found
python --version

REM Check Claude Code installation
if not exist "%USERPROFILE%\.claude" (
    echo [ERROR] Claude Code directory not found
    echo Please install Claude Code first
    pause
    exit /b 1
)

echo [OK] Claude Code directory found

REM Install Python dependencies
echo.
echo Installing Python dependencies with constraints.txt...
pip install -r requirements.txt -c constraints.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [OK] Dependencies installed

REM Create directories
echo.
echo Creating directory structure...
if not exist "%USERPROFILE%\.claude\hooks" mkdir "%USERPROFILE%\.claude\hooks"
if not exist "%USERPROFILE%\.claude\memory" mkdir "%USERPROFILE%\.claude\memory"
if not exist "%USERPROFILE%\.claude\memory\archive" mkdir "%USERPROFILE%\.claude\memory\archive"
if not exist "%USERPROFILE%\.claude\memory\outputs" mkdir "%USERPROFILE%\.claude\memory\outputs"

echo [OK] Directories created

REM Copy scripts
echo.
echo Copying scripts...
REM Deployed runtime is semantic-only: the l4_* wrappers invoke
REM l4_semantic_global.py (which imports chunking + ranking) and the hooks
REM import EncodingGate from memory_lint_helpers.py. Keep this set identical to
REM install.sh. Hybrid FTS5/BM25/rerank runs from the repo, not the flat
REM ~/.claude/hooks layout, so those modules are intentionally NOT deployed.
copy /Y "scripts\l4_semantic_global.py" "%USERPROFILE%\.claude\hooks\" >nul
copy /Y "scripts\chunking.py" "%USERPROFILE%\.claude\hooks\" >nul
copy /Y "scripts\ranking.py" "%USERPROFILE%\.claude\hooks\" >nul
REM memory_lint_helpers.py provides EncodingGate, imported by the hooks at
REM runtime. It MUST land next to the hooks (deployed layout is flat), or the
REM mojibake write-barrier silently disables itself.
copy /Y "scripts\memory_lint_helpers.py" "%USERPROFILE%\.claude\hooks\" >nul
REM Only the l4_* search/index wrappers are deployed. memory_lint.bat /
REM memory_lint_project.bat are intentionally NOT deployed: memory_lint.py is a
REM repo/dev tool with a rich dependency tree (antipattern_checkers,
REM consistency_checkers, utils/, config/) that doesn't fit the flat
REM ~/.claude/hooks layout. Run it from the cloned repo instead.
copy /Y "scripts\windows\l4_*.bat" "%USERPROFILE%\.claude\hooks\" >nul
copy /Y "hooks\git-activity-detector.py" "%USERPROFILE%\.claude\hooks\" >nul
copy /Y "hooks\stop_handoff_universal.py" "%USERPROFILE%\.claude\hooks\" >nul

REM Copy built-in hooks (essential for 4-layer memory to function)
REM These hooks provide: pre-compact flush, session logging, auto-remember,
REM context loading, encoding gate cache, and graceful shutdown wrapper.
copy /Y "hooks\builtin\*.py" "%USERPROFILE%\.claude\hooks\" >nul

echo [OK] Scripts and built-in hooks copied

REM Copy templates
echo.
echo Creating configuration templates...
if not exist "%USERPROFILE%\.claude\GLOBAL_PROJECTS.md" (
    copy /Y "templates\GLOBAL_PROJECTS.md.template" "%USERPROFILE%\.claude\GLOBAL_PROJECTS.md" >nul
    echo [OK] GLOBAL_PROJECTS.md created
) else (
    echo [SKIP] GLOBAL_PROJECTS.md already exists
)

REM Initialize memory structure
echo.
echo Initializing memory structure...
if not exist "%USERPROFILE%\.claude\memory\MEMORY.md" (
    copy /Y "templates\MEMORY.md.template" "%USERPROFILE%\.claude\memory\MEMORY.md" >nul
    echo [OK] MEMORY.md created
) else (
    echo [SKIP] MEMORY.md already exists
)

if not exist "%USERPROFILE%\.claude\memory\handoff.md" (
    copy /Y "templates\handoff.md.template" "%USERPROFILE%\.claude\memory\handoff.md" >nul
    echo [OK] handoff.md created
) else (
    echo [SKIP] handoff.md already exists
)

if not exist "%USERPROFILE%\.claude\memory\decisions.md" (
    copy /Y "templates\decisions.md.template" "%USERPROFILE%\.claude\memory\decisions.md" >nul
    echo [OK] decisions.md created
) else (
    echo [SKIP] decisions.md already exists
)

REM Test installation
echo.
echo Testing installation...
python "%USERPROFILE%\.claude\hooks\l4_semantic_global.py" stats >nul 2>&1
if errorlevel 1 (
    echo [WARN] L4 SEMANTIC test failed - this is normal on first run
) else (
    echo [OK] L4 SEMANTIC is working
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Edit %USERPROFILE%\.claude\GLOBAL_PROJECTS.md to add your projects
echo 2. Run: l4_index_all.bat to index your projects
echo 3. Run: l4_search_all.bat "query" to search
echo.
echo Documentation: docs\INSTALL.md
echo Usage guide: docs\guides\USAGE.md
echo.
pause
