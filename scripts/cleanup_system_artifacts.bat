@echo off
REM Cleanup System Artifacts - Windows Wrapper
REM Удаляет артефакты системных папок из ~/.claude/projects/

python "%~dp0cleanup_system_artifacts.py" %*
