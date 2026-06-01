# HOT Memory - Global Handoff

Последние глобальные события (не специфичные для проекта).

**Последнее обновление:** 2026-06-01 01:28
**Ротация:** 24 часа → decisions.md

---

## 2026-05-31 08:15 - Model Routing Protocol Hardened

**Project:** Global (C:\BAT)
**Duration:** ~15 minutes
**Status:** ✅ Завершено

**Проблема:**
- Claude систематически забывает применять model routing при чтении handoff.md в начале сессии
- N-я регрессия: протокол озвучивания контекста отвлекает от routing decision
- Чтение handoff.md воспринимается как "служебная" операция, не требующая routing

**Выполнено:**
1. **MANDATORY_CONTEXT_CHECK.md** - добавлен Шаг 2.5:
   - Явное требование применять model routing для чтения handoff.md
   - Протокол ДО/ВО ВРЕМЯ/ПОСЛЕ
   - Подчёркнуто: это НЕ служебная операция, исключений нет

2. **CLAUDE.md** - секция Model Routing полностью переписана:
   - Заголовок: "Model Routing (ОБЯЗАТЕЛЬНО применяется)"
   - Критическое правило: routing ОБЯЗАТЕЛЕН где тесты показали равное качество
   - Расширен список Haiku задач (handoff.md, git blame, линтеры, WebFetch)
   - Добавлена секция "Исключений НЕТ"
   - Нарушение протокола = регрессия качества работы

3. **Память обновлена:**
   - Создан `feedback_session_start_routing_regression.md`
   - Добавлен в MEMORY.md на первую позицию (⚠️ КРИТИЧНО)
   - Документированы: паттерн, причина, решение

**Следующие шаги:**
- Перезапуск для проверки применения усиленного протокола
- Верификация: Claude должен использовать Haiku для чтения handoff.md

---

## 2026-06-01 01:28 - Session completed

**Project:** BAT
**Duration:** 0 minutes
**Global changes:** 0

---

## 2026-06-01 01:25 - Session completed

**Project:** BAT
**Duration:** 0 minutes
**Global changes:** 0

---

## 2026-06-01 00:35 - Session completed

**Project:** BAT
**Duration:** 0 minutes
**Global changes:** 0

---

## 2026-05-28 13:37 - claude-4layer-memory v1.4.0 синхронизация завершена

**Project:** claude-4layer-memory
**Duration:** ~30 minutes (несколько сессий)
**Status:** ✅ Завершено

**Выполнено:**
1. **MR !32 применён** — все правки от Codex (коммит 6d33aac0)
   - Bug N-4 fix: RRF rel-path keys
   - Security fixes от ботов
2. **crash-recovery.py исправлен**
   - list-content / tool_result отсечены
   - injection-теги нейтрализуются
   - 20 unit-тестов добавлено
3. **Синхронизация из repo**
   - 4 файла из repo/scripts → ~/.claude/hooks/ И ~/.claude/scripts/
   - FTS5 + Chroma reindex выполнен

**Проблемы:**
- CI пайплайны падают на GitLab.com (нет runners, требует платёжный метод)

**Следующие шаги:**
- Мониторить CI статус
- stop_handoff/crash-recovery остаются локальными (не синхронизировать)
