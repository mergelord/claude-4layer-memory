#!/usr/bin/env python3
"""Clean bloated handoff.md files — removes noise entries (Git status spam)."""

import re
import shutil
from pathlib import Path
from datetime import datetime

NOISE_TITLES = ['Git статус проверен', 'Git stat']


def is_noise_entry(entry: str) -> bool:
    """Return True if entry is pure noise."""
    for title in NOISE_TITLES:
        if title in entry:
            return True
    if 'Session completed' in entry:
        zero_duration = 'Duration: 0 minutes' in entry
        zero_changes = 'Global changes: 0' in entry
        zero_files = 'Files modified: 0' in entry
        if zero_duration and (zero_changes or zero_files):
            return True
    return False


def parse_handoff(content: str) -> tuple[str, list[str]]:
    """Split handoff.md into header and list of entries."""
    separator_pos = content.find('\n---\n')
    if separator_pos == -1:
        return content, []
    header = content[:separator_pos + 5]
    entries_text = content[separator_pos + 5:]
    raw_entries = re.split(r'(?=\n## \d{4}-\d{2}-\d{2})', entries_text)
    entries = [e.strip() for e in raw_entries
               if e.strip() and e.strip().startswith('## 20')]
    return header, entries


def clean_handoff(filepath: Path) -> tuple[int, int]:
    """Clean one handoff.md. Returns (removed, kept)."""
    if not filepath.exists():
        return 0, 0
    content = filepath.read_text(encoding='utf-8', errors='replace')
    header, entries = parse_handoff(content)
    if not entries:
        return 0, 0
    total = len(entries)
    good = [e for e in entries if not is_noise_entry(e)]
    removed = total - len(good)
    if removed == 0:
        return 0, total
    # Backup
    shutil.copy2(filepath, filepath.with_suffix('.md.bak'))
    kept = good[-10:] if len(good) > 10 else good
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    if '**Последнее обновление:**' in header:
        parts = header.split('**Последнее обновление:**', 1)
        rest = parts[1].split('\n', 1)
        header = (parts[0] + f'**Последнее обновление:** {now}\n'
                  + (rest[1] if len(rest) > 1 else ''))
    new_content = header + '\n\n' + '\n\n'.join(kept) + '\n'
    filepath.write_text(new_content, encoding='utf-8')
    return removed, len(kept)


def main() -> None:
    """Find and clean all handoff.md files."""
    claude_dir = Path.home() / '.claude'
    targets: list[Path] = []
    global_handoff = claude_dir / 'memory' / 'handoff.md'
    if global_handoff.exists():
        targets.append(global_handoff)
    projects_dir = claude_dir / 'projects'
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            h = project_dir / 'memory' / 'handoff.md'
            if h.exists():
                targets.append(h)
    print(f"Found {len(targets)} handoff files\n")
    total_removed = 0
    for target in sorted(targets):
        removed, kept = clean_handoff(target)
        label = target.parent.parent.name
        if removed > 0:
            print(f"  CLEANED {label}: -{removed} noise, kept {kept}")
            total_removed += removed
        else:
            print(f"  OK      {label}: {kept} entries")
    print(f"\nTotal removed: {total_removed}")


if __name__ == '__main__':
    main()
