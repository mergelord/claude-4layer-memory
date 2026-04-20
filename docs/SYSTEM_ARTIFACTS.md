# System Artifacts in projects/

## Что это?

При запуске Claude Code CLI с **админскими правами** в Windows, рабочая директория (CWD) автоматически устанавливается в `C:\WINDOWS\system32`.

Claude Code CLI создаёт папку для session transcripts на основе CWD:
```
~/.claude/projects/C--WINDOWS-system32/
```

**Это не баг!** Это стандартное поведение:
- Windows устанавливает CWD в `system32` для админских процессов
- Claude Code CLI создаёт папку для хранения истории сессий
- Папка содержит `.jsonl` файлы (session transcripts)

## Аналогичные артефакты

Могут создаваться для других системных папок:
- `C--Program Files/`
- `C--Program Files (x86)/`
- `-usr-bin/` (Linux)
- `-etc/` (Linux)

## Нужно ли их удалять?

**Нет, если:**
- Вы регулярно работаете с админскими правами
- Хотите сохранить историю сессий
- Используете crash recovery

**Да, если:**
- Папка занимает много места (старые session transcripts)
- Хотите очистить артефакты

## Как удалить?

### Автоматически (рекомендуется)

```bash
# Dry run (показать что будет удалено)
python scripts/cleanup_system_artifacts.py --dry-run

# Реальное удаление
python scripts/cleanup_system_artifacts.py
```

### Вручную

```bash
rm -rf ~/.claude/projects/C--WINDOWS-system32/
rm -rf ~/.claude/projects/C-WINDOWS-system32/
```

**Важно:** Папка пересоздастся при следующем запуске с админскими правами.

## Как предотвратить создание?

**Невозможно.** Это встроенное поведение Claude Code CLI.

**Альтернатива:** Запускайте CLI без админских прав, если они не нужны. Тогда CWD будет `%USERPROFILE%` (C:\Users\MYRIG), а не `system32`.

## Влияние на систему памяти

**Никакого.** Система памяти использует:
- Глобальную память: `~/.claude/memory/`
- Проектную память: `~/.claude/projects/C--BAT-*/memory/`

Артефакты `C--WINDOWS-system32` не влияют на работу системы памяти.

---

**Дата:** 2026-04-20  
**Версия:** 1.0
