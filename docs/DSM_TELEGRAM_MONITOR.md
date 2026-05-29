# DSM Telegram Monitor

`scripts/dsm_telegram_monitor.py` sends DSM and `codex-lab` health updates to Telegram.
It uses only the Python standard library and talks to DSM over SSH.

## Configuration

Copy `config/dsm_telegram_monitor.example.json` to an ignored local file:

```powershell
Copy-Item config\dsm_telegram_monitor.example.json config\dsm_telegram_monitor.local.json
```

Fill in:

- `ssh.host`, `ssh.user`, `ssh.port`, `ssh.key_path`, `ssh.known_hosts`
- `telegram.bot_token`
- `telegram.chat_id`

The same values can be provided with environment variables:

- `DSM_SSH_HOST`
- `DSM_SSH_USER`
- `DSM_SSH_PORT`
- `DSM_SSH_KEY`
- `DSM_SSH_KNOWN_HOSTS`
- `DSM_TELEGRAM_BOT_TOKEN`
- `DSM_TELEGRAM_CHAT_ID`
- `DSM_MONITOR_CONTAINERS`
- `DSM_MONITOR_INTERVAL_SECONDS`
- `DSM_MONITOR_STATE_FILE`
- `DSM_MONITOR_DOCKER_PATH`

## Commands

Print current status:

```powershell
py -3.13 scripts\dsm_telegram_monitor.py --config config\dsm_telegram_monitor.local.json status
```

Print and send current status to Telegram:

```powershell
py -3.13 scripts\dsm_telegram_monitor.py --config config\dsm_telegram_monitor.local.json status --send
```

One-shot scheduled check. It sends Telegram only when state changes:

```powershell
py -3.13 scripts\dsm_telegram_monitor.py --config config\dsm_telegram_monitor.local.json check --send-initial
```

Long-running watcher:

```powershell
py -3.13 scripts\dsm_telegram_monitor.py --config config\dsm_telegram_monitor.local.json watch --send-initial
```

Send a Telegram connectivity test:

```powershell
py -3.13 scripts\dsm_telegram_monitor.py --config config\dsm_telegram_monitor.local.json test-telegram
```

## Notes

- Run the monitor outside DSM if you need an alert when DSM itself is unreachable.
- Run it on DSM only if you need detailed local container status and can tolerate no alert during a full DSM outage.
- The state file is stored under `.codex-temp/` by default and is ignored by Git.
