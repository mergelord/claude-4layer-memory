@echo off
REM L4 SEMANTIC - Search in global memory only
if "%~1"=="" (
    echo Usage: l4_search_global.bat "search query"
    exit /b 1
)
python "%USERPROFILE%\.claude\hooks\l4_semantic_global.py" search-global %*
