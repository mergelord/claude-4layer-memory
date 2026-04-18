@echo off
REM L4 SEMANTIC - Cleanup junk collections
python "%USERPROFILE%\.claude\hooks\l4_semantic_global.py" cleanup %*
