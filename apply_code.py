#!/usr/bin/env python3
"""
Читает код из входного файла, очищает и записывает в выходной.
Использование:
    python apply_code.py input.txt scripts/l4_semantic_global.py
"""
import sys
import re
from pathlib import Path

def clean_text(text: str) -> str:
    if text.startswith('\ufeff'):
        text = text[1:]
    text = re.sub(r'[\u200b\u200c\u200d\u00ad]', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [line.rstrip() for line in text.splitlines()]
    return '\n'.join(lines) + '\n'

def main():
    if len(sys.argv) < 3:
        print("Usage: python apply_code.py <input-file> <target-file>")
        print("Example: python apply_code.py temp_code.txt scripts/l4_semantic_global.py")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    target_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    raw = input_path.read_text('utf-8')
    cleaned = clean_text(raw)
    target_path.write_text(cleaned, 'utf-8')
    print(f"[OK] Cleaned code from {input_path} written to {target_path}")

if __name__ == "__main__":
    main()