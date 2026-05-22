#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Удаляет BOM и другие артефакты из файлов проекта. Выводит изменённые файлы."""

from pathlib import Path


def clean_file(file_path: Path) -> str | None:
    """Возвращает описание исправления, если были изменения, иначе None."""
    try:
        raw_bytes = file_path.read_bytes()
    except Exception as exc:
        print(f"  [SKIP] {file_path}: {exc}")
        return None

    fixes = []

    # Убираем BOM
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        raw_bytes = raw_bytes[3:]
        fixes.append("BOM UTF-8")
    elif raw_bytes.startswith(b'\xff\xfe'):
        raw_bytes = raw_bytes[2:]
        fixes.append("BOM UTF-16 LE")
    elif raw_bytes.startswith(b'\xfe\xff'):
        raw_bytes = raw_bytes[2:]
        fixes.append("BOM UTF-16 BE")

    # Удаляем нулевые байты
    if b'\x00' in raw_bytes:
        raw_bytes = raw_bytes.replace(b'\x00', b'')
        fixes.append("null bytes")

    # Удаляем невидимые управляющие символы (0x00-0x1F), кроме \n и \r
    cleaned = bytearray()
    for byte in raw_bytes:
        if byte < 0x20 and byte not in (0x0A, 0x0D):
            continue
        cleaned.append(byte)
    if len(cleaned) != len(raw_bytes):
        fixes.append("control chars")
        raw_bytes = bytes(cleaned)

    # Проверяем валидность UTF-8
    try:
        raw_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        fixes.append(f"invalid UTF-8 ({exc})")
        raw_bytes = raw_bytes.decode('utf-8', errors='replace').encode('utf-8')

    if not fixes:
        return None

    file_path.write_bytes(raw_bytes)
    return ", ".join(fixes)


def main():
    directories = ['scripts', 'tests', 'hooks', 'utils']
    root = Path('.')
    files_to_clean = []

    for d in directories:
        p = root / d
        if p.exists():
            files_to_clean.extend(p.rglob('*.py'))
            files_to_clean.extend(p.rglob('*.toml'))

    files_to_clean.extend(root.glob('*.py'))
    toml_file = root / 'ruff.toml'
    if toml_file.exists():
        files_to_clean.append(toml_file)

    if not files_to_clean:
        print("Не найдено файлов для очистки.")
        return

    print(f"Проверяю {len(files_to_clean)} файлов...\n")
    changed = 0
    for file_path in sorted(files_to_clean):
        if not file_path.is_file():
            continue
        fix_info = clean_file(file_path)
        if fix_info:
            print(f"  ИСПРАВЛЕН: {file_path} ({fix_info})")
            changed += 1

    if changed == 0:
        print("Все файлы чистые.")
    else:
        print(f"\nГотово. Исправлено файлов: {changed} из {len(files_to_clean)}.")


if __name__ == '__main__':
    main()