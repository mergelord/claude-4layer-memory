# Active Skills

Этот файл содержит активные skills для Claude Code.

## Как использовать

Skills загружаются автоматически через CLAUDE.md или можно ссылаться напрямую.

## Установленные Skills

### 1. Full-Output Enforcement
**Источник:** `~/.claude/skills/taste-skill/skills/output-skill/SKILL.md`
**Применение:** Всегда - для всех задач программирования

**Ключевые правила:**
- Запрещены placeholder паттерны: `// TODO`, `// ...`, `// rest of code`
- Запрещены фразы: "Let me know if you want me to continue"
- Требуется полная реализация без сокращений
- При длинных ответах - чистый breakpoint с `[PAUSED — X of Y complete]`

### 2. Minimalist UI
**Источник:** `~/.claude/skills/taste-skill/skills/minimalist-skill/SKILL.md`
**Применение:** При работе с GUI (tkinter, web UI)

**Ключевые правила:**
- Тёплая монохромная палитра (#F7F6F3, #111111)
- Типографический контраст (SF Pro Display, Geist Sans)
- Bento-grid layouts, минимальные тени
- Запрещены: градиенты, эмодзи, generic шрифты

### 3. Supabase Postgres Best Practices
**Источник:** `~/.claude/skills/supabase-skills/skills/supabase-postgres-best-practices/SKILL.md`
**Применение:** При работе с БД (если добавим в проекты)

**Категории:**
- Query Performance (CRITICAL)
- Connection Management (CRITICAL)
- Security & RLS (CRITICAL)
- Schema Design (HIGH)

## Как добавить новый skill

1. Клонировать репозиторий в `~/.claude/skills/`
2. Добавить запись в этот файл
3. Опционально: добавить в CLAUDE.md для автозагрузки


### 4. Surgical Changes
**Источник:** Karpathy-Inspired Guidelines (forrestchang/andrej-karpathy-skills)
**Применение:** Всегда — при редактировании существующего кода

**Ключевые правила:**
- Трогай только что относится к задаче
- Не улучшай соседний код, комментарии, форматирование
- Совпадай с существующим стилем
- Удали импорты/переменные которые ТВОИ изменения сделали неиспользуемыми
- Тест: каждая строка прямо относится к запросу

### 5. Goal-Driven Execution
**Источник:** Karpathy-Inspired Guidelines (forrestchang/andrej-karpathy-skills)
**Применение:** Многошаговые задачи

**Ключевые правила:**
- Трансформируй задачи в верифицируемые цели
- Формат плана: [Шаг] → verify: [проверка]
- Сильные критерии позволяют работать в цикле без уточнений

### 6. Simplicity First
**Источник:** Karpathy-Inspired Guidelines (forrestchang/andrej-karpathy-skills)
**Применение:** Перед написанием кода

**Ключевые правила:**
- Минимальный код решающий задачу, ничего спекулятивного
- Никаких абстракций для одноразового кода
- Тест: сказал бы senior engineer что это overcomplicated?

### 7. Think Before Coding
**Источник:** Karpathy-Inspired Guidelines (forrestchang/andrej-karpathy-skills)
**Применение:** Перед реализацией при неоднозначных задачах

**Ключевые правила:**
- Не угадывай — озвучивай допущения явно
- Если задача неоднозначна — представь несколько интерпретаций, не выбирай молча
- Если есть более простой подход — скажи об этом
- Если что-то непонятно — остановись и спроси
