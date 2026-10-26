"""Host-only bookkeeping. Standard library only; no database or Docker access."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
from zoneinfo import ZoneInfo

BACKUP = re.compile(r"dem-beta-(backup|preswap)-\d{8}T\d{12}Z-[0-9a-f]{8}\.dump\Z")
ROLLED_LOG = re.compile(r"access(?:-\d{4}-\d\d-\d\dT[\d.-]+\.log(?:\.gz)?|\.log-\d{8}(?:\.gz)?)\Z")


def calendars(schedule):
    match = re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([0-2]\d):([0-5]\d) (\S+)", schedule)
    if not match or int(match[2]) > 23:
        raise ValueError("invalid reset schedule")
    ZoneInfo(match[4])
    # The same wall clock / timezone / weekday as beta_admin.next_reset.
    reset = f"{match[1]} *-*-* {match[2]}:{match[3]}:00 {match[4]}"
    backup = f"*-*-* {(int(match[2]) + 2) % 24:02}:{match[3]}:00 {match[4]}"
    return reset, backup


def accumulate(previous, now, counter, boot, interface):
    if counter < 0:
        raise ValueError("negative interface counter")
    if previous and (set(previous) != {"month", "boot", "interface", "counter", "total"}
                     or any(type(previous[key]) is not int or previous[key] < 0 for key in ("counter", "total"))
                     or any(not isinstance(previous[key], str) or not previous[key] for key in ("month", "boot", "interface"))):
        raise ValueError("invalid traffic state")
    month = now.astimezone(timezone.utc).strftime("%Y-%m")
    same = previous.get("boot") == boot and previous.get("interface") == interface
    old_counter = previous.get("counter", 0)
    delta = counter - old_counter if same and counter >= old_counter else counter
    # Attribute an interval crossing midnight to the new month conservatively.
    total = previous.get("total", 0) if previous.get("month") == month else 0
    return dict(month=month, boot=boot, interface=interface, counter=counter, total=total + delta)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def traffic(home, interface):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", interface):
        raise ValueError("invalid network interface")
    path = home / "host-state" / "traffic.json"
    # Corruption fails closed: the shell freezes and stops web on watch failure.
    previous = json.loads(path.read_text()) if path.exists() else {}
    counter = int(Path(f"/sys/class/net/{interface}/statistics/tx_bytes").read_text())
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    value = accumulate(previous, datetime.now(timezone.utc), counter, boot, interface)
    atomic_json(path, value)
    return value["total"]


def prune_backups(directory):
    deleted = 0
    for kind in ("backup", "preswap"):
        paths = sorted(p for p in directory.iterdir()
                       if not p.is_symlink() and p.is_file()
                       and (match := BACKUP.fullmatch(p.name)) and match[1] == kind)
        # Keep the newest regular backup and preswap, even under disk pressure.
        for path in paths[:-1]:
            path.unlink()
            deleted += 1
    return deleted


def prune_logs(directory, now):
    for path in directory.iterdir():
        if (not path.is_symlink() and path.is_file() and ROLLED_LOG.fullmatch(path.name)
                and now - path.stat().st_mtime > 30 * 86400):
            path.unlink()


def install_units(source, destination, schedule):
    reset, backup = calendars(schedule)
    for path in source.iterdir():
        if path.suffix not in (".service", ".timer"):
            continue
        content = path.read_text().replace("@RESET_CALENDAR@", reset).replace("@BACKUP_CALENDAR@", backup)
        (destination / path.name).write_text(content)


def main():
    command, *args = sys.argv[1:]
    if command == "units":
        install_units(Path(args[0]), Path(args[1]), args[2])
    elif command in ("watch", "status"):
        home, interface = Path(args[0]), args[1]
        total = traffic(home, interface)
        usage = shutil.disk_usage(home)
        percent = 100 * usage.used // usage.total
        deleted = prune_backups(home / "backups") if command == "watch" and percent >= 90 else 0
        if command == "watch":
            prune_logs(home / "logs", datetime.now().timestamp())
        print(percent, total, deleted)
    else:
        raise ValueError("unknown host operation")


if __name__ == "__main__":
    main()
