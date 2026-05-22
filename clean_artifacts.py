#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Удаляет BOM и другие артефакты из файлов проекта."""

from pathlib import Path

def clean_file(file_path: Path) -> bool:
    try:
        raw_bytes = file_path.read_bytes()
    except Exception as exc:
        print(f"  [SKIP] {file_path}: {exc}")
        return False

    # Убираем BOM
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        raw_bytes = raw_bytes[3:]
        print(f"  BOM (UTF-8) удалён: {file_path.name}")
    elif raw_bytes.startswith(b'\xff\xfe'):
        raw_bytes = raw_bytes[2:]
        print(f"  BOM (UTF-16 LE) удалён: {file_path.name}")
    elif raw_bytes.startswith(b'\xfe\xff'):
        raw_bytes = raw_bytes[2:]
        print(f"  BOM (UTF-16 BE) удалён: {file_path.name}")

    # Удаляем нулевые байты
    if b'\x00' in raw_bytes:
        raw_bytes = raw_bytes.replace(b'\x00', b'')
        print(f"  Null bytes удалены: {file_path.name}")

    # Удаляем невидимые управляющие символы (0x00-0x1F), кроме \n и \r
    cleaned = bytearray()
    for byte in raw_bytes:
        if byte < 0x20 and byte not in (0x0A, 0x0D):
            continue
        cleaned.append(byte)
    if len(cleaned) != len(raw_bytes):
        print(f"  Управляющие символы удалены: {file_path.name}")
        raw_bytes = bytes(cleaned)

    # роверяем, что файл валидный UTF-8
    try:
        raw_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        print(f"  [WARN] екорректный UTF-8 в {file_path.name}: {exc}. опытка восстановления.")
        raw_bytes = raw_bytes.decode('utf-8', errors='replace').encode('utf-8')

    try:
        file_path.write_bytes(raw_bytes)
    except Exception as exc:
        print(f"  [ERROR] е удалось записать {file_path}: {exc}")
        return False

    return True

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
        print("е найдено файлов для очистки.")
        return

    print(f"роверяю {len(files_to_clean)} файлов...\n")
    fixed_count = 0
    for file_path in sorted(files_to_clean):
        if not file_path.is_file():
            continue
        if clean_file(file_path):
            fixed_count += 1

    print(f"\nотово. бработано файлов: {len(files_to_clean)}, исправлено: {fixed_count}.")

if __name__ == '__main__':
    main()
