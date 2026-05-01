#!/usr/bin/env python3
"""Universal Stop Hook - automatic handoff recording for all projects.

Records session summary to memory/handoff.md when session ends.
Automatically detects current project from CLAUDE_PROJECT_PATH or CWD.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from collections import Counter


def encode_project_path(project_path: Path) -> str:
    """РљРѕРґРёСЂСѓРµС‚ РїСѓС‚СЊ РїСЂРѕРµРєС‚Р° РґР»СЏ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ РІ РёРјРµРЅРё РґРёСЂРµРєС‚РѕСЂРёРё."""
    return str(project_path).replace(':', '').replace('\\', '-').replace('/', '-')


def detect_project():
    """РћРїСЂРµРґРµР»СЏРµС‚ С‚РµРєСѓС‰РёР№ РїСЂРѕРµРєС‚ РёР· РїРµСЂРµРјРµРЅРЅРѕР№ РѕРєСЂСѓР¶РµРЅРёСЏ РёР»Рё CWD."""
    # Blacklist СЃРёСЃС‚РµРјРЅС‹С… РїР°РїРѕРє (Р°СЂС‚РµС„Р°РєС‚С‹ Р·Р°РїСѓСЃРєР° РёР·-РїРѕРґ Р°РґРјРёРЅР°)
    SYSTEM_BLACKLIST = [
        'system32', 'System32', 'SYSTEM32',
        'Windows', 'WINDOWS', 'windows',
        'Program Files', 'Program Files (x86)',
        'ProgramData', 'AppData'
    ]

    # РџСЂРёРѕСЂРёС‚РµС‚ 1: CLAUDE_PROJECT_PATH
    project_path = os.getenv('CLAUDE_PROJECT_PATH')
    if project_path:
        resolved = Path(project_path).resolve()
        # РџСЂРѕРІРµСЂРєР° РЅР° СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё
        if any(blacklisted in str(resolved) for blacklisted in SYSTEM_BLACKLIST):
            return None  # РРіРЅРѕСЂРёСЂСѓРµРј СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё
        return resolved

    # РџСЂРёРѕСЂРёС‚РµС‚ 2: РўРµРєСѓС‰Р°СЏ РґРёСЂРµРєС‚РѕСЂРёСЏ
    cwd = Path.cwd()

    # РџСЂРѕРІРµСЂРєР° РЅР° СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё
    if any(blacklisted in str(cwd) for blacklisted in SYSTEM_BLACKLIST):
        return None  # РРіРЅРѕСЂРёСЂСѓРµРј СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё

    # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё CLAUDE.md РІ С‚РµРєСѓС‰РµР№ РґРёСЂРµРєС‚РѕСЂРёРё
    if (cwd / "CLAUDE.md").exists():
        return cwd

    # Fallback: РёСЃРїРѕР»СЊР·СѓРµРј CWD
    return cwd


def get_memory_paths(project_path: Path):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїСѓС‚Рё Рє С„Р°Р№Р»Р°Рј РїР°РјСЏС‚Рё РґР»СЏ РїСЂРѕРµРєС‚Р°."""
    encoded = encode_project_path(project_path)
    base = Path.home() / ".claude" / "projects" / encoded

    return {
        'activity_log': base / "activity.jsonl",
        'handoff': base / "memory" / "handoff.md",
        'session_start': base / ".session_start",
        'memory_dir': base / "memory"
    }


def parse_activity_log(activity_log: Path):
    """Parse activity.jsonl and extract statistics."""
    if not activity_log.exists():
        return None, [], Counter()

    activities = []
    try:
        with open(activity_log, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('```'):
                    continue
                if line.startswith('{') and line.endswith('}'):
                    try:
                        activities.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error reading activity log: {e}", file=sys.stderr)
        return None, [], Counter()

    # Extract modified files
    modified_files = set()
    for activity in activities:
        tool = activity.get('tool', '')
        args = activity.get('args', '')

        if tool in ('Edit', 'Write'):
            if '.py' in args or '.md' in args or '.json' in args or '.txt' in args:
                parts = args.split()
                for part in parts:
                    if '.' in part and '/' not in part[0:1]:
                        modified_files.add(part)
                        break

    # Count tools used
    tools_counter = Counter(activity.get('tool', 'Unknown') for activity in activities)

    return activities, sorted(modified_files), tools_counter


def calculate_duration(session_start_file: Path):
    """Calculate session duration in minutes."""
    if not session_start_file.exists():
        return 0

    try:
        with open(session_start_file, 'r', encoding='utf-8') as f:
            start_str = f.read().strip()

        start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        now = datetime.now(start_time.tzinfo)
        duration = (now - start_time).total_seconds() / 60
        return int(duration)
    except Exception as e:
        print(f"Error calculating duration: {e}", file=sys.stderr)
        return 0


def generate_summary(duration_min, activity_count, modified_files, tools_counter):
    """Generate handoff summary."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary = f"""## {now} - Session completed

**Duration:** {duration_min} minutes
**Activities:** {activity_count} tool calls
**Files modified:** {len(modified_files)}
"""

    if modified_files:
        summary += "\n**Files:**\n"
        for f in modified_files[:10]:
            summary += f"- {f}\n"

    if tools_counter:
        summary += "\n**Tools used:**\n"
        for tool, count in tools_counter.most_common(5):
            summary += f"- {tool}: {count}\n"

    summary += "\n---\n"

    return summary


def count_entries(content: str) -> int:
    """Count number of entries in handoff/decisions file."""
    return content.count('\n## 20')


def emergency_trim_handoff(handoff_file: Path, decisions_file: Path):
    """Emergency trim: if handoff > 10 entries, rotate oldest to decisions."""
    if not handoff_file.exists():
        return False

    content = handoff_file.read_text(encoding='utf-8')
    entry_count = count_entries(content)

    if entry_count <= 10:
        return False

    print(f"[TRIM] Handoff has {entry_count} entries, rotating oldest to decisions.md", file=sys.stderr)

    # Split into header and entries
    parts = content.split('---', 2)
    if len(parts) < 3:
        return False

    header = parts[0] + '---' + parts[1] + '---'
    entries_text = parts[2]

    # Parse entries
    entries = []
    current_entry = []
    for line in entries_text.split('\n'):
        if line.startswith('## 20') and current_entry:
            entries.append('\n'.join(current_entry))
            current_entry = [line]
        else:
            current_entry.append(line)
    if current_entry:
        entries.append('\n'.join(current_entry))

    # Keep newest 10, move rest to decisions
    keep_entries = entries[-10:]
    rotate_entries = entries[:-10]

    NOISE = ['Session completed', 'Git stat', 'Settings updated', 'Git СЃС‚Р°С‚СѓСЃ']
    # Filter NOISE from rotate_entries (don't pollute decisions.md)
    rotate_entries = [e for e in rotate_entries if not any(n in e for n in NOISE)]
    # Prefer meaningful entries in keep_entries too
    meaningful_keep = [e for e in keep_entries if not any(n in e for n in NOISE)]
    if meaningful_keep:
        keep_entries = meaningful_keep[-10:]
    elif keep_entries:
        keep_entries = keep_entries[-3:]  # All noise вЂ” keep only last 3
    if rotate_entries:
        # Append to decisions.md
        decisions_file.parent.mkdir(parents=True, exist_ok=True)
        if decisions_file.exists():
            decisions_content = decisions_file.read_text(encoding='utf-8')
        else:
            decisions_content = """# Decisions - WARM Memory

Р’Р°Р¶РЅС‹Рµ СЂРµС€РµРЅРёСЏ Рё РёР·РјРµРЅРµРЅРёСЏ Р·Р° РїРѕСЃР»РµРґРЅРёРµ 14 РґРЅРµР№.

**РћР±РЅРѕРІР»СЏРµС‚СЃСЏ:** РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё РёР· handoff.md (Р·Р°РїРёСЃРё СЃС‚Р°СЂС€Рµ 24С‡)
**Р РѕС‚Р°С†РёСЏ:** Р—Р°РїРёСЃРё СЃС‚Р°СЂС€Рµ 14 РґРЅРµР№ в†’ COLD (archive/)
**Р Р°Р·РјРµСЂ:** РќРµРѕРіСЂР°РЅРёС‡РµРЅ

---

"""

        # Insert rotated entries before last update line
        if '**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:**' in decisions_content:
            parts = decisions_content.rsplit('**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:**', 1)
            decisions_content = parts[0] + '\n'.join(rotate_entries) + '\n\n**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:**' + parts[1]
        else:
            decisions_content += '\n'.join(rotate_entries) + f"\n\n**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        decisions_file.write_text(decisions_content, encoding='utf-8')
        print(f"[TRIM] Rotated {len(rotate_entries)} entries to decisions.md", file=sys.stderr)

    # Update handoff with only newest entries
    new_content = header + '\n\n' + '\n\n'.join(keep_entries)
    new_content += f"\n\n**Р’СЃРµРіРѕ Р·Р°РїРёСЃРµР№:** {len(keep_entries)}/10\n"
    new_content += f"**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

    handoff_file.write_text(new_content, encoding='utf-8')
    return True


def emergency_trim_decisions(decisions_file: Path, memory_dir: Path):
    """Emergency trim: if decisions > 100 entries, rotate oldest to COLD."""
    if not decisions_file.exists():
        return False

    content = decisions_file.read_text(encoding='utf-8')
    entry_count = count_entries(content)

    if entry_count <= 100:
        return False

    print(f"[TRIM] Decisions has {entry_count} entries, rotating oldest to COLD", file=sys.stderr)

    # Create archive directory
    archive_dir = memory_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    # Split into header and entries
    parts = content.split('---', 2)
    if len(parts) < 3:
        return False

    header = parts[0] + '---' + parts[1] + '---'
    entries_text = parts[2]

    # Parse entries
    entries = []
    current_entry = []
    for line in entries_text.split('\n'):
        if line.startswith('## 20') and current_entry:
            entries.append('\n'.join(current_entry))
            current_entry = [line]
        else:
            current_entry.append(line)
    if current_entry:
        entries.append('\n'.join(current_entry))

    # Keep newest 100, move rest to COLD
    keep_entries = entries[-100:]
    rotate_entries = entries[:-100]

    if rotate_entries:
        # Save to archive
        archive_file = archive_dir / f"decisions_{datetime.now().strftime('%Y%m')}.md"
        if archive_file.exists():
            with open(archive_file, 'a', encoding='utf-8') as f:
                f.write('\n\n---\n\n')
                f.write('\n\n'.join(rotate_entries))
        else:
            with open(archive_file, 'w', encoding='utf-8') as f:
                f.write(f"# Archived Decisions - {datetime.now().strftime('%Y-%m')}\n\n")
                f.write("РђСЂС…РёРІРЅС‹Рµ СЂРµС€РµРЅРёСЏ, СЂРѕС‚РёСЂРѕРІР°РЅРЅС‹Рµ РёР· WARM РїР°РјСЏС‚Рё.\n\n---\n\n")
                f.write('\n\n'.join(rotate_entries))

        print(f"[TRIM] Rotated {len(rotate_entries)} entries to {archive_file.name}", file=sys.stderr)

        # Try to index in L4 SEMANTIC
        try:
            semantic_indexer = Path(__file__).parent / "semantic_indexer.py"
            if semantic_indexer.exists():
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(semantic_indexer), 'index', str(archive_file)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )
                if result.returncode == 0:
                    print("[L4] Indexed to semantic DB", file=sys.stderr)
        except Exception as e:
            print(f"[L4] Indexing skipped: {e}", file=sys.stderr)

    # Update decisions with only newest entries
    new_content = header + '\n\n' + '\n\n'.join(keep_entries)
    new_content += f"\n\n**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

    decisions_file.write_text(new_content, encoding='utf-8')
    return True


def update_handoff(handoff_file: Path, project_name: str, summary: str):
    """Insert summary into handoff.md after header."""
    # РЎРѕР·РґР°С‘Рј РґРёСЂРµРєС‚РѕСЂРёСЋ РµСЃР»Рё РЅРµС‚
    handoff_file.parent.mkdir(parents=True, exist_ok=True)

    # Backup
    if handoff_file.exists():
        backup = handoff_file.with_suffix('.md.bak')
        backup.write_text(handoff_file.read_text(encoding='utf-8'), encoding='utf-8')

    # Read existing content
    if handoff_file.exists():
        lines = handoff_file.read_text(encoding='utf-8').split('\n')
    else:
        # РЎРѕР·РґР°С‘Рј РЅРѕРІС‹Р№ С„Р°Р№Р»
        lines = [
            "# Handoff - HOT Memory",
            "",
            f"РџРѕСЃР»РµРґРЅРёРµ 10 РІР°Р¶РЅС‹С… СЃРѕР±С‹С‚РёР№ РІ РїСЂРѕРµРєС‚Рµ {project_name}.",
            "",
            "**РћР±РЅРѕРІР»СЏРµС‚СЃСЏ:** РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё РїСЂРё РІР°Р¶РЅС‹С… РёР·РјРµРЅРµРЅРёСЏС…",
            "**Р РѕС‚Р°С†РёСЏ:** Р—Р°РїРёСЃРё СЃС‚Р°СЂС€Рµ 24С‡ в†’ WARM (decisions.md)",
            "**Р Р°Р·РјРµСЂ:** РњР°РєСЃ 10 Р·Р°РїРёСЃРµР№",
            "",
            "---",
        ]

    # Find header end
    header_end = 9
    for i, line in enumerate(lines):
        if line.strip() == "---" and i < 15:
            header_end = i + 1
            break

    # Insert summary after header
    new_content = '\n'.join(lines[:header_end]) + '\n\n' + summary

    # Keep only recent entries
    if len(lines) > header_end:
        old_content = '\n'.join(lines[header_end:])
        new_content += old_content[:5000]

    # Write back
    handoff_file.write_text(new_content, encoding='utf-8')


def main():
    """Main entry point."""
    # Detect current project
    project_path = detect_project()
    paths = get_memory_paths(project_path)

    # Check if memory directory exists
    if not paths['memory_dir'].exists():
        # No memory setup for this project, skip
        sys.exit(0)

    # Parse activity log
    activities, modified_files, tools_counter = parse_activity_log(paths['activity_log'])

    if activities is None:
        sys.exit(0)

    # Calculate duration
    duration_min = calculate_duration(paths['session_start'])

    # Filter: only record if significant
    if duration_min < 5 and len(modified_files) == 0:
        sys.exit(0)

    # Generate summary
    summary = generate_summary(
        duration_min,
        len(activities),
        modified_files,
        tools_counter
    )

    # Update handoff.md
    try:
        update_handoff(paths['handoff'], project_path.name, summary)
        print(f"[OK] Updated handoff for {project_path.name}", file=sys.stderr)

        # Emergency trim if needed
        decisions_file = paths['memory_dir'] / "decisions.md"
        if emergency_trim_handoff(paths['handoff'], decisions_file):
            print("[OK] Emergency trim completed for handoff", file=sys.stderr)

        if emergency_trim_decisions(decisions_file, paths['memory_dir']):
            print("[OK] Emergency trim completed for decisions", file=sys.stderr)

    except Exception as e:
        print(f"Error updating handoff: {e}", file=sys.stderr)
        sys.exit(1)

    # Clean up
    if paths['session_start'].exists():
        paths['session_start'].unlink()

    # Rotate activity log
    if paths['activity_log'].exists() and len(activities) > 100:
        try:
            with open(paths['activity_log'], 'w', encoding='utf-8') as f:
                for activity in activities[-100:]:
                    f.write(json.dumps(activity) + '\n')
        except Exception as e:
            print(f"Error rotating activity log: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
