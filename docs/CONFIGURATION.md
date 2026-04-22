# Configuration Guide

## Memory Lint Configuration

Memory Lint использует `config/memory_lint_config.yml` для настройки пороговых значений валидации.

### Структура конфигурации

#### 1. Размеры файлов (`file_sizes`)

```yaml
file_sizes:
  max_size: 102400  # 100 KB - максимальный размер файла
  warn_size: 51200  # 50 KB - предупреждение о большом файле
```

**Назначение:** Контроль размера файлов памяти для предотвращения раздувания контекста.

**Рекомендации:**
- `max_size`: 100 KB достаточно для большинства файлов памяти
- Если файл превышает порог - разбейте его на несколько файлов

---

#### 2. Возраст записей (`age_thresholds`)

```yaml
age_thresholds:
  hot_max_hours: 24      # HOT записи старше 24 часов
  warm_max_days: 14      # WARM записи старше 14 дней
  cold_max_days: 30      # COLD записи старше 30 дней
  archive_max_days: 90   # Архивные записи старше 90 дней
```

**Назначение:** Автоматическая ротация записей между слоями памяти.

**Рекомендации:**
- HOT: 24 часа - для текущих событий
- WARM: 14 дней - для недавних решений
- COLD: 30 дней - для долгосрочного хранения
- Archive: 90 дней - для исторических данных

---

#### 3. Лимиты количества записей (`entry_limits`)

```yaml
entry_limits:
  hot_max_entries: 10    # Максимум записей в HOT
  warm_max_entries: 30   # Максимум записей в WARM
  cold_max_entries: 100  # Максимум записей в COLD
```

**Назначение:** Предотвращение переполнения слоёв памяти.

**Рекомендации:**
- HOT: 10 записей - только самое важное
- WARM: 30 записей - ключевые решения за 2 недели
- COLD: 100 записей - долгосрочная история

---

#### 4. Валидация frontmatter (`frontmatter`)

```yaml
frontmatter:
  required_fields:
    - name
    - description
    - type
  valid_types:
    - user
    - feedback
    - project
    - reference
```

**Назначение:** Проверка структуры метаданных файлов памяти.

**Обязательные поля:**
- `name`: Уникальное имя записи
- `description`: Краткое описание (для релевантности)
- `type`: Тип записи (user/feedback/project/reference)

---

#### 5. Проверка ссылок (`links`)

```yaml
links:
  check_external: true   # Проверять внешние ссылки
  check_internal: true   # Проверять внутренние ссылки
  timeout: 5             # Таймаут для внешних ссылок (секунды)
```

**Назначение:** Валидация ссылок в файлах памяти.

**Рекомендации:**
- `check_external: false` - если нет интернета
- `timeout: 5` - баланс между скоростью и надёжностью

---

#### 6. Уровни серьёзности (`severity`)

```yaml
severity:
  error: ERROR      # Критические ошибки (блокируют работу)
  warning: WARNING  # Предупреждения (требуют внимания)
  info: INFO        # Информационные сообщения
```

**Назначение:** Классификация проблем по важности.

---

#### 7. Быстрый режим (`quick_mode`)

```yaml
quick_mode:
  skip_external_links: true    # Пропускать проверку внешних ссылок
  skip_deep_validation: true   # Пропускать глубокую валидацию
  max_files_check: 50          # Максимум файлов для проверки
```

**Назначение:** Ускорение валидации для SessionStart hooks.

**Использование:**
```bash
python scripts/memory_lint.py --quick
```

---

## Кастомизация конфигурации

### Для конкретного проекта

Создайте `config/memory_lint_config.local.yml` (игнорируется git):

```yaml
# Переопределение для локального проекта
age_thresholds:
  hot_max_hours: 48  # Увеличить до 48 часов
  warm_max_days: 7   # Уменьшить до 7 дней
```

### Для CI/CD

Используйте переменные окружения:

```bash
export MEMORY_LINT_HOT_MAX_HOURS=12
export MEMORY_LINT_WARM_MAX_DAYS=7
python scripts/memory_lint.py
```

---

## Примеры использования

### 1. Строгая валидация (для production)

```yaml
file_sizes:
  max_size: 51200  # 50 KB

age_thresholds:
  hot_max_hours: 12
  warm_max_days: 7
  cold_max_days: 14

entry_limits:
  hot_max_entries: 5
  warm_max_entries: 15
  cold_max_entries: 50
```

### 2. Мягкая валидация (для development)

```yaml
file_sizes:
  max_size: 204800  # 200 KB

age_thresholds:
  hot_max_hours: 48
  warm_max_days: 30
  cold_max_days: 90

entry_limits:
  hot_max_entries: 20
  warm_max_entries: 50
  cold_max_entries: 200
```

### 3. Быстрая валидация (для hooks)

```yaml
quick_mode:
  skip_external_links: true
  skip_deep_validation: true
  max_files_check: 20
```

---

## Troubleshooting

### Проблема: "Config file not found"

**Решение:** Создайте `config/memory_lint_config.yml` из шаблона:

```bash
cp config/memory_lint_config.yml.example config/memory_lint_config.yml
```

### Проблема: "Invalid YAML syntax"

**Решение:** Проверьте синтаксис YAML:

```bash
python -c "import yaml; yaml.safe_load(open('config/memory_lint_config.yml'))"
```

### Проблема: "Missing required field"

**Решение:** Убедитесь что все обязательные поля присутствуют:

```yaml
frontmatter:
  required_fields:
    - name
    - description
    - type
```

---

## Best Practices

1. **Не изменяйте дефолтные значения без причины** - они оптимизированы для большинства случаев
2. **Используйте `.local.yml` для экспериментов** - не коммитьте локальные изменения
3. **Документируйте изменения** - добавляйте комментарии в YAML
4. **Тестируйте после изменений** - запускайте `memory_lint.py` после каждого изменения
5. **Версионируйте конфиг** - коммитьте изменения в git с понятными сообщениями

---

## См. также

- [ARCHITECTURE.md](ARCHITECTURE.md) - Архитектура системы памяти
- [USAGE.md](USAGE.md) - Руководство пользователя
- [MEMORY_LINT.md](MEMORY_LINT.md) - Детали работы Memory Lint
