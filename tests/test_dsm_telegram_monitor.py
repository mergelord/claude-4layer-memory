from pathlib import Path

from scripts import dsm_telegram_monitor as monitor


def test_shell_quote_handles_single_quotes():
    assert monitor.shell_quote("codex'lab") == "'codex'\"'\"'lab'"


def test_load_config_from_environment():
    env = {
        "DSM_SSH_HOST": "dsm.example.test",
        "DSM_SSH_USER": "jbsergie",
        "DSM_SSH_PORT": "22756",
        "DSM_SSH_KEY": "C:/tmp/key",
        "DSM_SSH_KNOWN_HOSTS": ".codex-temp/known_hosts",
        "DSM_TELEGRAM_BOT_TOKEN": "token",
        "DSM_TELEGRAM_CHAT_ID": "123",
        "DSM_MONITOR_CONTAINERS": "codex-lab,sidecar",
        "DSM_MONITOR_INTERVAL_SECONDS": "60",
    }

    config = monitor.load_config(None, env)

    assert config.ssh.host == "dsm.example.test"
    assert config.ssh.user == "jbsergie"
    assert config.ssh.port == 22756
    assert config.ssh.key_path == "C:/tmp/key"
    assert config.ssh.known_hosts == ".codex-temp/known_hosts"
    assert config.telegram is not None
    assert config.telegram.chat_id == "123"
    assert config.containers == ("codex-lab", "sidecar")
    assert config.interval_seconds == 60


def test_load_config_from_file(tmp_path):
    config_file = tmp_path / "monitor.json"
    config_file.write_text(
        """
{
  "ssh": {"host": "dsm.local", "user": "user", "port": 2222},
  "containers": ["codex-lab"],
  "state_file": "state.json"
}
""".strip(),
        encoding="utf-8",
    )

    config = monitor.load_config(config_file, {})

    assert config.ssh.host == "dsm.local"
    assert config.ssh.port == 2222
    assert config.telegram is None
    assert config.state_file == Path("state.json")


def test_build_ssh_command_uses_argument_list():
    ssh = monitor.SshConfig(
        host="dsm.local",
        user="user",
        port=22756,
        key_path="C:/tmp/key",
        known_hosts=".codex-temp/known_hosts",
    )

    command = monitor.build_ssh_command(ssh, "echo ok")

    assert command[0] == "ssh"
    assert command[-2:] == ["user@dsm.local", "echo ok"]
    assert "-i" in command
    assert "C:/tmp/key" in command
    assert "StrictHostKeyChecking=yes" in command


def test_parse_container_status_running():
    result = monitor.CommandResult(
        returncode=0,
        stdout="\n".join(
            [
                "status=running",
                "running=true",
                "restarting=false",
                "exit_code=0",
                "started_at=2026-05-29T00:00:00Z",
                "restart_count=2",
                "image=node:22-bookworm-slim",
            ]
        ),
        stderr="",
    )

    status = monitor.parse_container_status("codex-lab", result)

    assert status.running is True
    assert status.status == "running"
    assert status.restart_count == 2
    assert status.image == "node:22-bookworm-slim"


def test_collect_snapshot_marks_ssh_unreachable():
    config = monitor.MonitorConfig(
        ssh=monitor.SshConfig(host="dsm.local", user="user"),
        telegram=None,
    )

    def runner(_ssh, _remote_command, _timeout):
        return monitor.CommandResult(255, "", "connection failed")

    snapshot = monitor.collect_snapshot(config, timeout=1, runner=runner)

    assert snapshot.errors == ("ssh_unreachable: connection failed",)
    assert monitor.snapshot_has_alert(snapshot) is True


def test_snapshot_state_changes_on_restart_count():
    first = monitor.Snapshot(
        checked_at="2026-05-29T00:00:00Z",
        host={"hostname": "dsm"},
        errors=(),
        containers=(
            monitor.ContainerStatus(
                name="codex-lab",
                status="running",
                running=True,
                restarting=False,
                exit_code=0,
                started_at="start",
                restart_count=1,
                image="node",
            ),
        ),
    )
    second = monitor.Snapshot(
        checked_at="2026-05-29T00:01:00Z",
        host={"hostname": "dsm"},
        errors=(),
        containers=(
            monitor.ContainerStatus(
                name="codex-lab",
                status="running",
                running=True,
                restarting=False,
                exit_code=0,
                started_at="start",
                restart_count=2,
                image="node",
            ),
        ),
    )

    assert monitor.snapshot_state(first) != monitor.snapshot_state(second)


def test_should_notify_only_initial_when_requested():
    current = {"reachable": True}

    assert monitor.should_notify(None, current, send_initial=False) is False
    assert monitor.should_notify(None, current, send_initial=True) is True
    assert monitor.should_notify({"reachable": False}, current, send_initial=False) is True
