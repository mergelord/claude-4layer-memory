# Anti-patterns Fixes - 2026-04-22

## Что исправили

### HIGH severity (3 → 0)
1. `feedback_cognee_incompatibility.md` - изменён формат `## Why` → `**Why:**`
2. `feedback_skill_creation_protocol.md` - изменён формат `## Why` → `**Why:**`
3. `feedback_testing_workflow.md` - изменён формат `## Why` → `**Why:**`

### MEDIUM severity (оставлено как есть)
1. `decisions.md` - 4 code blocks (контекст решений)
2. `feedback_testing_workflow.md` - 12 code blocks (примеры команд для документации)

## Результат

```
Before: HIGH: 3, MEDIUM: 2, LOW: 0
After:  HIGH: 0, MEDIUM: 2, LOW: 0
```

✅ Все критичные anti-patterns исправлены!

## Детали проверки

Anti-patterns detection корректно находит:
- Missing `**Why:**`/`**How to apply:**` в feedback/project типах
- Excessive code blocks (>3)
- Vague descriptions
- Temporary data в permanent слоях
- Undated claims
- Git history duplication
