# GitHub Actions Workflows

Автоматические CI/CD процессы для claude-4layer-memory.

## Workflows

### 1. Python Tests (`test.yml`)
**Триггер:** Push и Pull Request в `main`

**Что делает:**
- Тестирует на 3 ОС: Ubuntu, Windows, macOS
- Тестирует на Python 3.8, 3.9, 3.10, 3.11, 3.12
- Устанавливает зависимости
- Проверяет, что скрипты запускаются (`--help`)
- Проверяет executable права на Linux/Mac

**Зачем:** Гарантирует, что проект работает на всех платформах

### 2. Shellcheck (`shellcheck.yml`)
**Триггер:** Push и Pull Request в `main`

**Что делает:**
- Проверяет bash скрипты в `scripts/linux/`
- Проверяет `install.sh`, `audit.sh`
- Находит ошибки и потенциальные проблемы

**Зачем:** Качество bash скриптов, предотвращение багов

### 3. Release (`release.yml`)
**Триггер:** Push тега вида `v*.*.*` (например, `v1.2.0`)

**Что делает:**
- Генерирует changelog из git commits
- Создаёт GitHub Release
- Прикрепляет файлы: скрипты, шаблоны, install скрипты

**Зачем:** Автоматическая публикация релизов

## Как использовать

### Запустить тесты локально
```bash
# Установить зависимости
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Проверить скрипты
python scripts/memory_lint.py --help
python audit.py --help
```

### Создать релиз
```bash
# Создать тег
git tag v1.2.0

# Запушить тег
git push origin v1.2.0

# GitHub Actions автоматически создаст Release
```

### Проверить bash скрипты локально
```bash
# Установить shellcheck
# Ubuntu: sudo apt install shellcheck
# Mac: brew install shellcheck
# Windows: scoop install shellcheck

# Проверить скрипты
shellcheck scripts/linux/*.sh
shellcheck install.sh
```

## Статус workflows

Badges можно добавить в README.md:

```markdown
![Python Tests](https://github.com/mergelord/claude-4layer-memory/actions/workflows/test.yml/badge.svg)
![Shellcheck](https://github.com/mergelord/claude-4layer-memory/actions/workflows/shellcheck.yml/badge.svg)
```

## Troubleshooting

**Тесты падают на Windows:**
- Проверь пути (используй `/` вместо `\`)
- Проверь encoding файлов (должен быть UTF-8)

**Shellcheck находит ошибки:**
- Исправь по рекомендациям
- Или добавь `# shellcheck disable=SC####` если ложное срабатывание

**Release не создаётся:**
- Проверь формат тега: должен быть `v1.2.3`
- Проверь права: нужен `GITHUB_TOKEN` (автоматически есть)
