#!/usr/bin/env python3
"""
Git Activity Detector - РѕС‚СЃР»РµР¶РёРІР°РµС‚ git РєРѕРјР°РЅРґС‹ Рё Р·Р°РїРёСЃС‹РІР°РµС‚ РІ РїР°РјСЏС‚СЊ.

РўСЂРёРіРіРµСЂС‹:
- git init в†’ "РџСЂРѕРµРєС‚ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ"
- git commit в†’ "РљРѕРјРјРёС‚: <message>"
- git push в†’ "Push РІ <remote>/<branch>"
- РЎРѕР·РґР°РЅРёРµ/РёР·РјРµРЅРµРЅРёРµ .gitignore в†’ "РќР°СЃС‚СЂРѕРµРЅР° Р·Р°С‰РёС‚Р° РѕС‚ СЃР»СѓС‡Р°Р№РЅС‹С… РєРѕРјРјРёС‚РѕРІ"
- git remote add в†’ "Р”РѕР±Р°РІР»РµРЅ remote: <url>"

Р—Р°РїРёСЃС‹РІР°РµС‚ РІ:
- РџСЂРѕРµРєС‚РЅСѓСЋ РїР°РјСЏС‚СЊ (РІСЃРµРіРґР°)
- Р“Р»РѕР±Р°Р»СЊРЅСѓСЋ РїР°РјСЏС‚СЊ (РµСЃР»Рё РїСѓР±Р»РёС‡РЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№ РёР»Рё РІР°Р¶РЅРѕРµ СЃРѕР±С‹С‚РёРµ)
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path


def get_cwd():
    """РџРѕР»СѓС‡Р°РµС‚ С‚РµРєСѓС‰СѓСЋ СЂР°Р±РѕС‡СѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ."""
    return Path(os.getcwd())


def detect_project():
    """РћРїСЂРµРґРµР»СЏРµС‚ РїСЂРѕРµРєС‚ РёР· CWD."""
    # Blacklist СЃРёСЃС‚РµРјРЅС‹С… РїР°РїРѕРє
    SYSTEM_BLACKLIST = [
        'system32', 'System32', 'SYSTEM32',
        'Windows', 'WINDOWS', 'windows',
        'Program Files', 'Program Files (x86)',
        'ProgramData', 'AppData'
    ]

    cwd = get_cwd()

    # РџСЂРѕРІРµСЂРєР° РЅР° СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё
    if any(blacklisted in str(cwd) for blacklisted in SYSTEM_BLACKLIST):
        return None  # РРіРЅРѕСЂРёСЂСѓРµРј СЃРёСЃС‚РµРјРЅС‹Рµ РїР°РїРєРё

    # РС‰РµРј Р±Р»РёР¶Р°Р№С€РёР№ .git РёР»Рё РёСЃРїРѕР»СЊР·СѓРµРј CWD
    current = cwd
    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent

    return cwd


def get_memory_paths(project_path):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїСѓС‚Рё Рє РїР°РјСЏС‚Рё РїСЂРѕРµРєС‚Р°."""
    # РљРѕРґРёСЂСѓРµРј РїСѓС‚СЊ РїСЂРѕРµРєС‚Р°
    encoded = str(project_path).replace(':', '-').replace('\\', '-').replace('/', '-')
    base = Path.home() / ".claude" / "projects" / encoded / "memory"

    return {
        'handoff': base / "handoff.md",
        'decisions': base / "decisions.md",
        'memory_dir': base,
        'activity_log': Path.home() / ".claude" / "activity.log"
    }


def get_global_memory_paths():
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїСѓС‚Рё Рє РіР»РѕР±Р°Р»СЊРЅРѕР№ РїР°РјСЏС‚Рё."""
    base = Path.home() / ".claude" / "memory"
    return {
        'handoff': base / "handoff.md",
        'decisions': base / "decisions.md",
        'memory_dir': base
    }


def run_git_command(cmd, cwd=None):
    """Р’С‹РїРѕР»РЅСЏРµС‚ git РєРѕРјР°РЅРґСѓ Рё РІРѕР·РІСЂР°С‰Р°РµС‚ СЂРµР·СѓР»СЊС‚Р°С‚."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", 1


def detect_git_activity(project_path):
    """
    РћРїСЂРµРґРµР»СЏРµС‚ git Р°РєС‚РёРІРЅРѕСЃС‚СЊ РІ РїСЂРѕРµРєС‚Рµ.

    Р’РѕР·РІСЂР°С‰Р°РµС‚ dict СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ git Р°РєС‚РёРІРЅРѕСЃС‚Рё.
    """
    activity = {
        'has_git': False,
        'has_remote': False,
        'remote_url': None,
        'is_public': False,
        'last_commit': None,
        'last_commit_message': None,
        'branch': None,
        'uncommitted_changes': False,
        'gitignore_exists': False
    }

    # РџСЂРѕРІРµСЂРєР° РЅР°Р»РёС‡РёСЏ .git
    if not (project_path / '.git').exists():
        return activity

    activity['has_git'] = True

    # РўРµРєСѓС‰Р°СЏ РІРµС‚РєР°
    branch, rc = run_git_command(['git', 'branch', '--show-current'], cwd=project_path)
    if rc == 0:
        activity['branch'] = branch

    # Remote
    remote_output, rc = run_git_command(['git', 'remote', '-v'], cwd=project_path)
    if rc == 0 and remote_output:
        activity['has_remote'] = True
        # РџР°СЂСЃРёРј URL
        lines = remote_output.split('\n')
        for line in lines:
            if 'origin' in line and '(push)' in line:
                parts = line.split()
                if len(parts) >= 2:
                    activity['remote_url'] = parts[1]
                    # РћРїСЂРµРґРµР»СЏРµРј РїСѓР±Р»РёС‡РЅРѕСЃС‚СЊ
                    if 'github.com' in parts[1] or 'gitlab.com' in parts[1]:
                        activity['is_public'] = True
                    break

    # РџРѕСЃР»РµРґРЅРёР№ РєРѕРјРјРёС‚
    commit_hash, rc = run_git_command(['git', 'rev-parse', 'HEAD'], cwd=project_path)
    if rc == 0:
        activity['last_commit'] = commit_hash[:7]

        # РЎРѕРѕР±С‰РµРЅРёРµ РєРѕРјРјРёС‚Р°
        msg, rc = run_git_command(['git', 'log', '-1', '--pretty=%s'], cwd=project_path)
        if rc == 0:
            activity['last_commit_message'] = msg

    # Uncommitted changes
    status, rc = run_git_command(['git', 'status', '--porcelain'], cwd=project_path)
    if rc == 0 and status:
        activity['uncommitted_changes'] = True

    # .gitignore
    if (project_path / '.gitignore').exists():
        activity['gitignore_exists'] = True

    return activity


def parse_activity_log():
    """
    РџР°СЂСЃРёС‚ activity.log РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РїРѕСЃР»РµРґРЅРёС… git РєРѕРјР°РЅРґ.

    Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє git СЃРѕР±С‹С‚РёР№.
    """
    activity_log = Path.home() / ".claude" / "activity.log"
    if not activity_log.exists():
        return []

    events = []

    try:
        with open(activity_log, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # РС‰РµРј Bash РєРѕРјР°РЅРґС‹ СЃ git
                    if entry.get('tool') == 'Bash':
                        command = entry.get('input', {}).get('command', '')

                        # git init
                        if 'git init' in command:
                            events.append({
                                'type': 'init',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git commit
                        elif 'git commit' in command:
                            events.append({
                                'type': 'commit',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git push
                        elif 'git push' in command:
                            events.append({
                                'type': 'push',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                        # git remote add
                        elif 'git remote add' in command:
                            events.append({
                                'type': 'remote_add',
                                'command': command,
                                'timestamp': entry.get('timestamp')
                            })

                    # РС‰РµРј Write/Edit РґР»СЏ .gitignore
                    elif entry.get('tool') in ['Write', 'Edit']:
                        file_path = entry.get('input', {}).get('file_path', '')
                        if '.gitignore' in file_path:
                            events.append({
                                'type': 'gitignore',
                                'file': file_path,
                                'timestamp': entry.get('timestamp')
                            })

                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"[ERROR] Failed to parse activity log: {e}", file=sys.stderr)

    return events


def generate_git_summary(project_path, git_activity, git_events):
    """Р“РµРЅРµСЂРёСЂСѓРµС‚ СЃРІРѕРґРєСѓ git Р°РєС‚РёРІРЅРѕСЃС‚Рё РґР»СЏ РїР°РјСЏС‚Рё."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary_parts = []

    # Р—Р°РіРѕР»РѕРІРѕРє
    if git_events:
        event_types = [e['type'] for e in git_events]
        if 'init' in event_types:
            title = "Git СЂРµРїРѕР·РёС‚РѕСЂРёР№ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ"
        elif 'push' in event_types:
            title = "Push РІ СѓРґР°Р»С‘РЅРЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№"
        elif 'commit' in event_types:
            title = "РЎРѕР·РґР°РЅ git РєРѕРјРјРёС‚"
        elif 'gitignore' in event_types:
            title = ".gitignore РЅР°СЃС‚СЂРѕРµРЅ"
        else:
            title = "Git Р°РєС‚РёРІРЅРѕСЃС‚СЊ"
    else:
        title = "Git СЃС‚Р°С‚СѓСЃ РїСЂРѕРІРµСЂРµРЅ"

    summary_parts.append(f"## {now} - {title}\n")

    # РРЅС„РѕСЂРјР°С†РёСЏ Рѕ РїСЂРѕРµРєС‚Рµ
    if git_activity['has_git']:
        summary_parts.append(f"**РџСЂРѕРµРєС‚:** {project_path.name}")

        if git_activity['branch']:
            summary_parts.append(f"**Р’РµС‚РєР°:** {git_activity['branch']}")

        if git_activity['has_remote']:
            summary_parts.append(f"**Remote:** {git_activity['remote_url']}")
            if git_activity['is_public']:
                summary_parts.append("**РЎС‚Р°С‚СѓСЃ:** вњ… РџСѓР±Р»РёС‡РЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№")
            else:
                summary_parts.append("**РЎС‚Р°С‚СѓСЃ:** рџ”’ РџСЂРёРІР°С‚РЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№")
        else:
            summary_parts.append("**Remote:** РќРµС‚ (Р»РѕРєР°Р»СЊРЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№)")

        if git_activity['last_commit']:
            summary_parts.append(f"**РџРѕСЃР»РµРґРЅРёР№ РєРѕРјРјРёС‚:** {git_activity['last_commit']}")
            if git_activity['last_commit_message']:
                summary_parts.append(f"**РЎРѕРѕР±С‰РµРЅРёРµ:** {git_activity['last_commit_message']}")

        if git_activity['gitignore_exists']:
            summary_parts.append("**Р—Р°С‰РёС‚Р°:** .gitignore РЅР°СЃС‚СЂРѕРµРЅ")

    # РЎРѕР±С‹С‚РёСЏ
    if git_events:
        summary_parts.append("\n**РЎРѕР±С‹С‚РёСЏ:**")
        for event in git_events[-5:]:  # РџРѕСЃР»РµРґРЅРёРµ 5
            if event['type'] == 'init':
                summary_parts.append("- РРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ git СЂРµРїРѕР·РёС‚РѕСЂРёР№")
            elif event['type'] == 'commit':
                summary_parts.append("- РЎРѕР·РґР°РЅ РєРѕРјРјРёС‚")
            elif event['type'] == 'push':
                summary_parts.append("- Push РІ СѓРґР°Р»С‘РЅРЅС‹Р№ СЂРµРїРѕР·РёС‚РѕСЂРёР№")
            elif event['type'] == 'remote_add':
                summary_parts.append("- Р”РѕР±Р°РІР»РµРЅ remote")
            elif event['type'] == 'gitignore':
                summary_parts.append("- РћР±РЅРѕРІР»С‘РЅ .gitignore")

    summary_parts.append("\n---\n")

    return "\n".join(summary_parts)


def is_global_worthy(git_activity, git_events):
    if not git_events:
        return False
    important=['init','push','remote_add','commit']
    return any(e['type'] in important for e in git_events)


def update_memory(memory_file: Path, new_entry: str):
    """РћР±РЅРѕРІР»СЏРµС‚ С„Р°Р№Р» РїР°РјСЏС‚Рё."""
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    if not memory_file.exists():
        # РЎРѕР·РґР°С‘Рј РЅРѕРІС‹Р№ С„Р°Р№Р»
        header = """# HOT Memory - Handoff

РџРѕСЃР»РµРґРЅРёРµ СЃРѕР±С‹С‚РёСЏ Рё РєРѕРЅС‚РµРєСЃС‚ РїСЂРѕРµРєС‚Р° (РѕРєРЅРѕ 24 С‡Р°СЃР°).

**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:** {now}

---

""".format(now=datetime.now().strftime("%Y-%m-%d %H:%M"))
        content = header + new_entry
    else:
        # Р§РёС‚Р°РµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№
        content = memory_file.read_text(encoding='utf-8')

        # РћР±РЅРѕРІР»СЏРµРј timestamp
        if '**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:**' in content:
            parts = content.split('**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:**')
            before = parts[0]
            after = parts[1].split('\n', 1)
            content = before + f"**РџРѕСЃР»РµРґРЅРµРµ РѕР±РЅРѕРІР»РµРЅРёРµ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + after[1]

        # Р”РѕР±Р°РІР»СЏРµРј РЅРѕРІСѓСЋ Р·Р°РїРёСЃСЊ РїРѕСЃР»Рµ СЂР°Р·РґРµР»РёС‚РµР»СЏ
        if '---' in content:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                content = parts[0] + '---' + parts[1] + '---\n\n' + new_entry + parts[2]
            else:
                content += '\n' + new_entry
        else:
            content += '\n' + new_entry

    memory_file.write_text(content, encoding='utf-8')


def main():
    """Main entry point."""
    try:
        # РћРїСЂРµРґРµР»СЏРµРј РїСЂРѕРµРєС‚
        project_path = detect_project()

        # Check for system directories (blacklist)
        if project_path is None:
            return 0

        # РџРѕР»СѓС‡Р°РµРј РїСѓС‚Рё Рє РїР°РјСЏС‚Рё
        project_memory = get_memory_paths(project_path)
        global_memory = get_global_memory_paths()

        # РћРїСЂРµРґРµР»СЏРµРј git Р°РєС‚РёРІРЅРѕСЃС‚СЊ
        git_activity = detect_git_activity(project_path)

        # РџР°СЂСЃРёРј activity log РґР»СЏ git СЃРѕР±С‹С‚РёР№
        git_events = parse_activity_log()

                # Р•СЃР»Рё РЅРµС‚ git СЃРѕР±С‹С‚РёР№ (commit/push/init/remote_add) - РІС‹С…РѕРґРёРј
        # РџСЂРѕРІРµСЂСЏРµРј С‚РѕР»СЊРєРѕ git_events, РќР• has_git
        # РРЅР°С‡Рµ РєР°Р¶РґР°СЏ СЃРµСЃСЃРёСЏ РїРёС€РµС‚ "Git СЃС‚Р°С‚СѓСЃ РїСЂРѕРІРµСЂРµРЅ" РґР°Р¶Рµ Р±РµР· РґРµР№СЃС‚РІРёР№
        if not git_events:
            return 0
         
        # Р“РµРЅРµСЂРёСЂСѓРµРј СЃРІРѕРґРєСѓ
        summary = generate_git_summary(project_path, git_activity, git_events)

        # Р—Р°РїРёСЃС‹РІР°РµРј РІ РїСЂРѕРµРєС‚РЅСѓСЋ РїР°РјСЏС‚СЊ
        update_memory(project_memory['handoff'], summary)
        print("[OK] Git activity recorded to project memory", file=sys.stderr)

        # РџСЂРѕРІРµСЂСЏРµРј, РЅСѓР¶РЅРѕ Р»Рё Р·Р°РїРёСЃС‹РІР°С‚СЊ РІ РіР»РѕР±Р°Р»СЊРЅСѓСЋ РїР°РјСЏС‚СЊ
        if is_global_worthy(git_activity, git_events):
            update_memory(global_memory['handoff'], summary)
            print("[GLOBAL] Git activity recorded to global memory", file=sys.stderr)

        return 0

    except Exception as e:
        print(f"[ERROR] Git activity detector failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
