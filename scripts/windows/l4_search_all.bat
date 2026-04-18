@echo off
REM L4 SEMANTIC - Search across all projects
if "%~1"=="" (
    echo Usage: l4_search_all.bat "search query"
    exit /b 1
)
python "%USERPROFILE%\.claude\hooks\l4_semantic_global.py" search-all %*
