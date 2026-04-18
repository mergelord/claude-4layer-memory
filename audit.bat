@echo off
REM Claude 4-Layer Memory System - Pre-Installation Audit (Windows)

echo.
echo Running pre-installation audit...
echo.

python audit.py

if errorlevel 1 (
    echo.
    echo [ERROR] Audit found critical issues
    echo Please resolve them before installing
    pause
    exit /b 1
)

echo.
echo [OK] Audit passed! Ready to install.
echo.
echo Run install.bat to proceed with installation
pause
