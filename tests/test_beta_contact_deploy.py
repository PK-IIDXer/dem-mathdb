"""Contact-only mount and host notification integration; all commands stubbed."""
import json
import os
import subprocess

import pytest

from test_beta_deploy_config import BASH, DEPLOY, compose, shell_host

SEED_DATABASE = "sqlite"


def test_contact_mount_is_api_only_and_secret_never_enters_container():
    config = compose()
    mounts = []
    for name, service in config["services"].items():
        assert not any("SLACK" in key or "WEBHOOK" in key for key in service.get("environment", {}))
        assert "env_file" not in service
        mounts.extend((name, mount) for mount in service.get("volumes", []) if "/contacts" in mount)
    assert mounts == [("api", "${DEM_BETA_HOME:?set runtime directory}/contacts:/beta/contacts:rw")]
    for network in config["services"]["api"]["networks"]:
        assert config["networks"][network]["internal"] is True
    assert config["services"]["api"]["read_only"] is True
    ignore = (DEPLOY / "api.Dockerfile.dockerignore").read_text()
    assert "!deploy/beta/notify.py" not in ignore
    assert "notify.py" not in (DEPLOY / "api.Dockerfile").read_text()


def test_notification_timer_installed_enabled_but_not_started():
    timer = (DEPLOY / "systemd/dem-beta-notify.timer").read_text()
    service = (DEPLOY / "systemd/dem-beta-notify.service").read_text()
    installer = (DEPLOY / "install.sh").read_text()
    assert "OnBootSec=5min" in timer and "OnUnitActiveSec=5min" in timer
    assert "ExecStart=/usr/local/sbin/dem-beta notify" in service and "UMask=0077" in service
    enable = next(line for line in installer.splitlines() if line.startswith("systemctl enable dem-beta-reset.timer"))
    assert "dem-beta-notify.timer" in enable and "--now" not in enable
    assert 'install -d -m 0700 -o 10001 -g 10001 "$DEM_BETA_HOME/contacts"' in installer
    assert "DEM_BETA_SLACK_WEBHOOK_URL=<slack-incoming-webhook-url>" in (DEPLOY / ".env.example").read_text()


@pytest.mark.parametrize("failed", [False, True])
def test_reset_calls_record_only_notify_without_changing_reset_result(shell_host, failed):
    directory, _, environment = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "reset"],
                            env=dict(environment, FAIL_AT="reset prepare" if failed else "", FAIL_NOTIFY="1"),
                            capture_output=True, timeout=20)
    assert (result.returncode != 0) == failed
    calls = (directory / "notify-calls").read_text()
    assert "notify.py" in calls and "--record-only" in calls


@pytest.mark.parametrize("stats,flags", [("84 100 0", "84 0 0 0"), ("85 100 0", "85 1 0 0"), ("90 2500000000000 0", "90 1 1 0")])
def test_watch_records_all_alert_conditions_without_network(shell_host, stats, flags):
    directory, _, environment = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "watch"],
                            env=dict(environment, TEST_STATS=stats, FAIL_NOTIFY="1"), capture_output=True, timeout=20)
    assert result.returncode == 0
    assert "--record-only --watch " + flags in (directory / "notify-calls").read_text()


def test_notify_command_does_not_acquire_operation_lock_or_use_docker(shell_host):
    directory, _, environment = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "notify"], env=environment,
                            capture_output=True, timeout=20)
    assert result.returncode == 0
    assert not (directory / "calls").exists()
    assert "--record-only" not in (directory / "notify-calls").read_text()
