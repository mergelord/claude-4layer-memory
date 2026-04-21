@echo off
REM ============================================================================
REM Комплексный анализ архитектуры Claude 4-Layer Memory System
REM ============================================================================

setlocal enabledelayedexpansion

echo ============================================================================
echo              Architecture Analysis - Claude 4-Layer Memory
echo ============================================================================
echo.

set "REPORT_DIR=reports\architecture"
set "TIMESTAMP=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"

REM Создание директории для отчётов
if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"

echo [1/7] Установка необходимых инструментов...
echo.

pip install -q radon wily vulture cohesion pydeps pipdeptree 2>nul
if errorlevel 1 (
    echo [WARNING] Некоторые пакеты не установлены, продолжаем с доступными...
)

echo.
echo ============================================================================
echo [2/7] Radon - Cyclomatic Complexity
echo ============================================================================
echo.

radon cc . -a -s --total-average --exclude="tests/*,__pycache__/*" > "%REPORT_DIR%\radon_complexity_%TIMESTAMP%.txt"
radon cc . -a -s --total-average --exclude="tests/*,__pycache__/*"

echo.
echo ============================================================================
echo [3/7] Radon - Maintainability Index
echo ============================================================================
echo.

radon mi . -s --exclude="tests/*,__pycache__/*" > "%REPORT_DIR%\radon_maintainability_%TIMESTAMP%.txt"
radon mi . -s --exclude="tests/*,__pycache__/*"

echo.
echo ============================================================================
echo [4/7] Radon - Raw Metrics (LOC, LLOC, Comments)
echo ============================================================================
echo.

radon raw . -s --exclude="tests/*,__pycache__/*" > "%REPORT_DIR%\radon_raw_%TIMESTAMP%.txt"
radon raw . -s --exclude="tests/*,__pycache__/*"

echo.
echo ============================================================================
echo [5/7] Vulture - Dead Code Detection
echo ============================================================================
echo.

vulture . --min-confidence 80 --exclude="tests/*,__pycache__/*" > "%REPORT_DIR%\vulture_deadcode_%TIMESTAMP%.txt" 2>&1
type "%REPORT_DIR%\vulture_deadcode_%TIMESTAMP%.txt"

echo.
echo ============================================================================
echo [6/7] Cohesion - Class Cohesion Metrics
echo ============================================================================
echo.

cohesion -d . --exclude="tests/*,__pycache__/*" > "%REPORT_DIR%\cohesion_%TIMESTAMP%.txt" 2>&1
type "%REPORT_DIR%\cohesion_%TIMESTAMP%.txt"

echo.
echo ============================================================================
echo [7/7] Pydeps - Dependency Graph
echo ============================================================================
echo.

echo Генерация графа зависимостей (может занять время)...
pydeps . --max-bacon=3 --no-show --exclude tests __pycache__ -o "%REPORT_DIR%\dependency_graph_%TIMESTAMP%.svg" 2>nul
if exist "%REPORT_DIR%\dependency_graph_%TIMESTAMP%.svg" (
    echo [OK] Граф сохранён: %REPORT_DIR%\dependency_graph_%TIMESTAMP%.svg
) else (
    echo [SKIP] Pydeps недоступен или произошла ошибка
)

echo.
echo ============================================================================
echo                              Summary Report
echo ============================================================================
echo.

echo Отчёты сохранены в: %REPORT_DIR%\
echo.
echo Файлы:
dir /b "%REPORT_DIR%\*%TIMESTAMP%*"

echo.
echo ============================================================================
echo [DONE] Анализ завершён
echo ============================================================================
echo.
echo Для просмотра детального отчёта:
echo   - Complexity: type reports\architecture\radon_complexity_%TIMESTAMP%.txt
echo   - Maintainability: type reports\architecture\radon_maintainability_%TIMESTAMP%.txt
echo   - Dead Code: type reports\architecture\vulture_deadcode_%TIMESTAMP%.txt
echo   - Dependency Graph: start reports\architecture\dependency_graph_%TIMESTAMP%.svg
echo.

pause
