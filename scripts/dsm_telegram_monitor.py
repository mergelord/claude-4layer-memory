#!/usr/bin/env python3
"""
DSM/codex-lab monitor with Telegram notifications.

The script intentionally uses only the Python standard library. It can run as a
one-shot scheduled check or as a long-running watcher.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


DEFAULT_CONTAINERS = ("codex-lab",)
DEFAULT_DOCKER_PATH = "/usr/local/bin/docker"
DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_STATE_FILE = Path(".codex-temp") / "dsm_telegram_monitor_state.json"


class ConfigError(RuntimeError):
    """Raised when monitor configuration is incomplete or invalid."""


class TelegramError(RuntimeError):
    """Raised when Telegram API call fails."""


@dataclass(frozen=True)
class SshConfig:
    host: str
    user: str
    port: int = 22
    key_path: str | None = None
    known_hosts: str | None = None
    strict_host_key_checking: bool = True
    connect_timeout: int = 10
    ssh_path: str = "ssh"


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str
    api_base: str = "https://api.telegram.org"


@dataclass(frozen=True)
class MonitorConfig:
    ssh: SshConfig
    telegram: TelegramConfig | None
    containers: tuple[str, ...] = DEFAULT_CONTAINERS
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    state_file: Path = DEFAULT_STATE_FILE
    docker_path: str = DEFAULT_DOCKER_PATH


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ContainerStatus:
    name: str
    status: str
    running: bool
    restarting: bool
    exit_code: int | None
    started_at: str
    restart_count: int | None
    image: str
    error: str = ""


@dataclass(frozen=True)
class Snapshot:
    checked_at: str
    host: dict[str, str]
    containers: tuple[ContainerStatus, ...]
    errors: tuple[str, ...]


RemoteRunner = Callable[[SshConfig, str, int], CommandResult]


def shell_quote(value: str) -> str:
    """Quote a string for a POSIX remote shell command."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_key_value_lines(output: str) -> dict[str, str]:
    values = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_bool(value: str | None) -> bool:
    return str(value or "").lower() == "true"


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def compact_error(result: CommandResult) -> str:
    text = (result.stderr or result.stdout or "").strip()
    if not text:
        return f"remote command failed with exit code {result.returncode}"
    return " ".join(text.split())[:500]


def load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a JSON object: {path}")
    return data


def get_section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = data.get(name, {})
    if not isinstance(section, Mapping):
        raise ConfigError(f"Config section must be an object: {name}")
    return section


def get_setting(
    env: Mapping[str, str],
    section: Mapping[str, Any],
    env_name: str,
    *keys: str,
    default: Any = None,
) -> Any:
    value = env.get(env_name)
    if value not in (None, ""):
        return value
    for key in keys:
        if section.get(key) not in (None, ""):
            return section[key]
    return default


def require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing required setting: {name}")
    return value.strip()


def require_https_url(value: Any, name: str) -> str:
    url = require_string(value, name).rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ConfigError(f"Setting must be an HTTPS URL without credentials: {name}")
    return url


def parse_positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Setting must be an integer: {name}") from exc
    if parsed <= 0:
        raise ConfigError(f"Setting must be positive: {name}")
    return parsed


def parse_bool_setting(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"Boolean setting has invalid value: {value}")


def parse_containers(data: Mapping[str, Any], env: Mapping[str, str]) -> tuple[str, ...]:
    raw_env = env.get("DSM_MONITOR_CONTAINERS")
    if raw_env:
        containers = [part.strip() for part in raw_env.split(",")]
    else:
        raw_config = data.get("containers", DEFAULT_CONTAINERS)
        if isinstance(raw_config, str):
            containers = [part.strip() for part in raw_config.split(",")]
        elif isinstance(raw_config, list):
            containers = [str(part).strip() for part in raw_config]
        else:
            raise ConfigError("containers must be a list or comma-separated string")
    cleaned = tuple(container for container in containers if container)
    if not cleaned:
        raise ConfigError("At least one container must be configured")
    return cleaned


def load_config(config_path: Path | None, env: Mapping[str, str] | None = None) -> MonitorConfig:
    env_map = os.environ if env is None else env
    data = load_json_file(config_path)
    ssh_section = get_section(data, "ssh")
    telegram_section = get_section(data, "telegram")

    host = require_string(
        get_setting(env_map, ssh_section, "DSM_SSH_HOST", "host"),
        "DSM_SSH_HOST or ssh.host",
    )
    user = require_string(
        get_setting(env_map, ssh_section, "DSM_SSH_USER", "user"),
        "DSM_SSH_USER or ssh.user",
    )
    port = parse_positive_int(
        get_setting(env_map, ssh_section, "DSM_SSH_PORT", "port", default=22),
        "DSM_SSH_PORT or ssh.port",
    )
    connect_timeout = parse_positive_int(
        get_setting(env_map, ssh_section, "DSM_SSH_CONNECT_TIMEOUT", "connect_timeout", default=10),
        "DSM_SSH_CONNECT_TIMEOUT or ssh.connect_timeout",
    )
    strict_host_key_checking = parse_bool_setting(
        get_setting(
            env_map,
            ssh_section,
            "DSM_SSH_STRICT_HOST_KEY_CHECKING",
            "strict_host_key_checking",
            default=True,
        ),
        default=True,
    )
    ssh = SshConfig(
        host=host,
        user=user,
        port=port,
        key_path=get_setting(env_map, ssh_section, "DSM_SSH_KEY", "key_path"),
        known_hosts=get_setting(env_map, ssh_section, "DSM_SSH_KNOWN_HOSTS", "known_hosts"),
        strict_host_key_checking=strict_host_key_checking,
        connect_timeout=connect_timeout,
        ssh_path=str(get_setting(env_map, ssh_section, "DSM_SSH_PATH", "ssh_path", default="ssh")),
    )

    token = get_setting(env_map, telegram_section, "DSM_TELEGRAM_BOT_TOKEN", "bot_token", "token")
    chat_id = get_setting(env_map, telegram_section, "DSM_TELEGRAM_CHAT_ID", "chat_id")
    telegram = None
    if token or chat_id:
        telegram = TelegramConfig(
            token=require_string(token, "DSM_TELEGRAM_BOT_TOKEN or telegram.bot_token"),
            chat_id=require_string(chat_id, "DSM_TELEGRAM_CHAT_ID or telegram.chat_id"),
            api_base=require_https_url(
                get_setting(
                    env_map,
                    telegram_section,
                    "DSM_TELEGRAM_API_BASE",
                    "api_base",
                    default="https://api.telegram.org",
                ),
                "DSM_TELEGRAM_API_BASE or telegram.api_base",
            ),
        )

    interval = parse_positive_int(
        get_setting(env_map, data, "DSM_MONITOR_INTERVAL_SECONDS", "interval_seconds", default=300),
        "DSM_MONITOR_INTERVAL_SECONDS or interval_seconds",
    )
    state_file = Path(
        str(
            get_setting(
                env_map,
                data,
                "DSM_MONITOR_STATE_FILE",
                "state_file",
                default=str(DEFAULT_STATE_FILE),
            )
        )
    )
    docker_path = require_string(
        get_setting(env_map, data, "DSM_MONITOR_DOCKER_PATH", "docker_path", default=DEFAULT_DOCKER_PATH),
        "DSM_MONITOR_DOCKER_PATH or docker_path",
    )
    return MonitorConfig(
        ssh=ssh,
        telegram=telegram,
        containers=parse_containers(data, env_map),
        interval_seconds=interval,
        state_file=state_file,
        docker_path=docker_path,
    )


def build_ssh_command(ssh: SshConfig, remote_command: str) -> list[str]:
    command = [
        ssh.ssh_path,
        "-p",
        str(ssh.port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={ssh.connect_timeout}",
        "-o",
        f"StrictHostKeyChecking={'yes' if ssh.strict_host_key_checking else 'no'}",
    ]
    if ssh.known_hosts:
        command.extend(["-o", f"UserKnownHostsFile={ssh.known_hosts}"])
    if ssh.key_path:
        command.extend(["-i", ssh.key_path])
    command.extend([f"{ssh.user}@{ssh.host}", remote_command])
    return command


def run_remote_command(ssh: SshConfig, remote_command: str, timeout: int) -> CommandResult:
    try:
        result = subprocess.run(
            build_ssh_command(ssh, remote_command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(returncode=124, stdout="", stderr=str(exc))
    return CommandResult(result.returncode, result.stdout, result.stderr)


def build_host_command() -> str:
    disk_probe = (
        "printf 'disk=%s\\n' "
        "\"$(df -h /volume1 2>/dev/null | awk 'NR==2 {print $3\"/\"$2\" (\"$5\" used)\"}')\""
    )
    memory_probe = (
        "printf 'memory=%s\\n' "
        "\"$(free -m 2>/dev/null | awk '/Mem:/ "
        "{print $3\"MB/\"$2\"MB (\"int($3*100/$2)\"% used)\"}')\""
    )
    return " ; ".join(
        [
            "printf 'hostname=%s\\n' \"$(hostname 2>/dev/null || echo unknown)\"",
            "printf 'uptime=%s\\n' \"$(uptime -p 2>/dev/null || uptime 2>/dev/null || echo unknown)\"",
            "printf 'load=%s\\n' \"$(cat /proc/loadavg 2>/dev/null | awk '{print $1\" \"$2\" \"$3}')\"",
            disk_probe,
            memory_probe,
        ]
    )


def build_container_command(container_name: str, docker_path: str) -> str:
    inspect_format = "\n".join(
        [
            "status={{.State.Status}}",
            "running={{.State.Running}}",
            "restarting={{.State.Restarting}}",
            "exit_code={{.State.ExitCode}}",
            "started_at={{.State.StartedAt}}",
            "restart_count={{.RestartCount}}",
            "image={{.Config.Image}}",
        ]
    )
    return " ; ".join(
        [
            f"DOCKER={shell_quote(docker_path)}",
            'if [ ! -x "$DOCKER" ]; then DOCKER="$(command -v docker || true)"; fi',
            'if [ -z "$DOCKER" ]; then printf "error=docker_not_found\\n"; exit 0; fi',
            f'"$DOCKER" inspect --format {shell_quote(inspect_format)} {shell_quote(container_name)}',
        ]
    )


def parse_container_status(name: str, result: CommandResult) -> ContainerStatus:
    if result.returncode != 0:
        return ContainerStatus(
            name=name,
            status="error",
            running=False,
            restarting=False,
            exit_code=None,
            started_at="",
            restart_count=None,
            image="",
            error=compact_error(result),
        )
    values = parse_key_value_lines(result.stdout)
    error = values.get("error", "")
    return ContainerStatus(
        name=name,
        status=values.get("status", "unknown") if not error else "error",
        running=parse_bool(values.get("running")) and not error,
        restarting=parse_bool(values.get("restarting")),
        exit_code=parse_int(values.get("exit_code")),
        started_at=values.get("started_at", ""),
        restart_count=parse_int(values.get("restart_count")),
        image=values.get("image", ""),
        error=error,
    )


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def collect_snapshot(
    config: MonitorConfig,
    timeout: int,
    runner: RemoteRunner = run_remote_command,
) -> Snapshot:
    host_result = runner(config.ssh, build_host_command(), timeout)
    if host_result.returncode != 0:
        return Snapshot(
            checked_at=utc_timestamp(),
            host={},
            containers=(),
            errors=(f"ssh_unreachable: {compact_error(host_result)}",),
        )

    host = parse_key_value_lines(host_result.stdout)
    containers = []
    for name in config.containers:
        result = runner(config.ssh, build_container_command(name, config.docker_path), timeout)
        containers.append(parse_container_status(name, result))
    return Snapshot(
        checked_at=utc_timestamp(),
        host=host,
        containers=tuple(containers),
        errors=(),
    )


def snapshot_has_alert(snapshot: Snapshot) -> bool:
    return bool(snapshot.errors) or any(not container.running for container in snapshot.containers)


def snapshot_state(snapshot: Snapshot) -> dict[str, Any]:
    return {
        "reachable": not snapshot.errors,
        "errors": list(snapshot.errors),
        "containers": {
            container.name: {
                "status": container.status,
                "running": container.running,
                "restarting": container.restarting,
                "exit_code": container.exit_code,
                "restart_count": container.restart_count,
                "error": container.error,
            }
            for container in snapshot.containers
        },
    }


def format_snapshot(snapshot: Snapshot, title: str = "DSM monitor status") -> str:
    state = "ALERT" if snapshot_has_alert(snapshot) else "OK"
    lines = [title, f"State: {state}", f"Checked: {snapshot.checked_at}"]

    if snapshot.host:
        lines.append("")
        lines.append("Host:")
        for key in ("hostname", "uptime", "load", "disk", "memory"):
            value = snapshot.host.get(key)
            if value:
                lines.append(f"- {key}: {value}")

    if snapshot.errors:
        lines.append("")
        lines.append("Errors:")
        for error in snapshot.errors:
            lines.append(f"- {error}")

    if snapshot.containers:
        lines.append("")
        lines.append("Containers:")
        for container in snapshot.containers:
            status = "OK" if container.running else "ALERT"
            details = [
                f"- {container.name}: {status}",
                f"status={container.status}",
            ]
            if container.image:
                details.append(f"image={container.image}")
            if container.restart_count is not None:
                details.append(f"restarts={container.restart_count}")
            if container.exit_code is not None:
                details.append(f"exit={container.exit_code}")
            if container.started_at:
                details.append(f"started={container.started_at}")
            if container.error:
                details.append(f"error={container.error}")
            lines.append(", ".join(details))

    return "\n".join(lines)


def load_state(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        return data
    return None


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def should_notify(previous: Mapping[str, Any] | None, current: Mapping[str, Any], send_initial: bool) -> bool:
    if previous is None:
        return send_initial
    return dict(previous) != dict(current)


def require_telegram(config: MonitorConfig) -> TelegramConfig:
    if config.telegram is None:
        raise ConfigError("Telegram settings are required for this command")
    return config.telegram


def split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < 1:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    chunks.append(remaining)
    return chunks


def send_telegram_message(telegram: TelegramConfig, text: str, timeout: int = 30) -> None:
    url = f"{telegram.api_base}/bot{telegram.token}/sendMessage"
    for chunk in split_telegram_text(text):
        payload = json.dumps(
            {
                "chat_id": telegram.chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                response_data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise TelegramError(f"Telegram send failed: {exc}") from exc
        if not response_data.get("ok"):
            raise TelegramError(f"Telegram API rejected message: {response_data}")


def run_status(config: MonitorConfig, args: argparse.Namespace) -> int:
    snapshot = collect_snapshot(config, args.timeout)
    message = format_snapshot(snapshot)
    print(message)
    if args.send:
        send_telegram_message(require_telegram(config), message, timeout=args.timeout)
    return 1 if snapshot_has_alert(snapshot) else 0


def run_check(config: MonitorConfig, args: argparse.Namespace) -> int:
    snapshot = collect_snapshot(config, args.timeout)
    current_state = snapshot_state(snapshot)
    previous_state = load_state(config.state_file)
    notify = should_notify(previous_state, current_state, args.send_initial)
    message = format_snapshot(snapshot, title="DSM monitor changed")

    if args.dry_run or notify:
        print(message)
    if notify and not args.dry_run:
        send_telegram_message(require_telegram(config), message, timeout=args.timeout)
    save_state(config.state_file, current_state)
    return 0


def run_watch(config: MonitorConfig, args: argparse.Namespace) -> int:
    if not args.dry_run:
        require_telegram(config)
    while True:
        try:
            run_check(config, args)
        except (ConfigError, TelegramError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
        time.sleep(config.interval_seconds)


def run_test_telegram(config: MonitorConfig, args: argparse.Namespace) -> int:
    message = "DSM Telegram monitor test message"
    send_telegram_message(require_telegram(config), message, timeout=args.timeout)
    print("Telegram test message sent")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor DSM/codex-lab and send Telegram alerts")
    parser.add_argument("--config", type=Path, help="Path to JSON config file")
    parser.add_argument("--timeout", type=int, default=30, help="SSH and Telegram timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Print current DSM/container status")
    status_parser.add_argument("--send", action="store_true", help="Also send the status to Telegram")

    check_parser = subparsers.add_parser("check", help="Send Telegram only when monitored state changes")
    check_parser.add_argument(
        "--send-initial",
        action="store_true",
        help="Send a message when no state exists yet",
    )
    check_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print instead of sending Telegram messages",
    )

    watch_parser = subparsers.add_parser("watch", help="Run repeated checks forever")
    watch_parser.add_argument(
        "--send-initial",
        action="store_true",
        help="Send a message when no state exists yet",
    )
    watch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print instead of sending Telegram messages",
    )

    subparsers.add_parser("test-telegram", help="Send a Telegram test message")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "status":
            return run_status(config, args)
        if args.command == "check":
            return run_check(config, args)
        if args.command == "watch":
            return run_watch(config, args)
        if args.command == "test-telegram":
            return run_test_telegram(config, args)
    except (ConfigError, TelegramError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
