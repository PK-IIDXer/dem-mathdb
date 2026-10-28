"""Root-terminal-only incident summary and firewall argv; never execute rules."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys


def ipv4(value):
    if not isinstance(value, str):
        raise ValueError("IPv4 must be a textual address")
    return str(ipaddress.IPv4Address(value))


def firewall_argv(address, interface):
    address = ipv4(address)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,14}", interface):
        raise ValueError("Invalid interface name")
    match = ["-i", interface, "-s", address + "/32", "-j", "DROP"]
    return {"block": ["iptables", "-I", "DOCKER-USER", "1", *match],
            "check": ["iptables", "-C", "DOCKER-USER", *match],
            "unblock": ["iptables", "-D", "DOCKER-USER", *match]}


def summarize(lines, minutes, now):
    if not math.isfinite(minutes) or minutes <= 0:
        raise ValueError("minutes must be finite and positive")
    counts, ignored = {}, 0
    for line in lines:
        try:
            row = json.loads(line)
            stamp, status = row["ts"], row["status"]
            if (isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp)
                    or type(status) is not int or not 100 <= status <= 599):
                raise ValueError("Invalid log fields")
            address = ipv4(row["request"]["remote_ip"])
        except (ValueError, TypeError, KeyError):
            ignored += 1
            continue
        if now - minutes * 60 <= stamp <= now:
            counts.setdefault(address, Counter())[status] += 1
    return {"minutes": minutes, "ignored_invalid_rows": ignored,
            "sources": [{"remote_ip": address, "total": sum(values.values()),
                         "statuses": dict(sorted(values.items()))}
                        for address, values in sorted(counts.items(), key=lambda item: (-sum(item[1].values()), item[0]))]}


def require_root_terminal():
    if getattr(os, "geteuid", lambda: -1)() != 0 or not sys.stdout.isatty():
        raise PermissionError("Use a root terminal only; do not redirect or share incident IP data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summary")
    summary.add_argument("--minutes", type=float, default=5)
    summary.add_argument("--log", type=Path, action="append")
    block = commands.add_parser("block-commands")
    block.add_argument("--ip", required=True)
    block.add_argument("--interface", required=True)
    args = parser.parse_args()
    require_root_terminal()
    if args.command == "block-commands":
        result = firewall_argv(args.ip, args.interface)
    else:
        def lines():
            for path in args.log or [Path("/var/lib/dem-beta/logs/access.log")]:
                opener = gzip.open if path.suffix == ".gz" else open
                with opener(path, "rt", encoding="utf-8") as stream:
                    yield from stream
        result = summarize(lines(), args.minutes, datetime.now(timezone.utc).timestamp())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
