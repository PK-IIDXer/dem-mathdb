from __future__ import annotations

import argparse
import locale
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
OUTCOME_PATTERN = re.compile(
    r"(?P<count>\d+) "
    r"(?P<name>passed|failed|skipped|errors?|xfailed|xpassed|deselected)"
)


@dataclass(frozen=True)
class StageResult:
    name: str
    return_code: int
    counts: dict[str, int]
    no_tests_accepted: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 or self.no_tests_accepted

    @property
    def executed(self) -> int:
        return sum(
            count
            for outcome, count in self.counts.items()
            if outcome != "deselected"
        )


def _parse_counts(output: str) -> dict[str, int]:
    for line in reversed(output.splitlines()):
        matches = list(OUTCOME_PATTERN.finditer(line))
        if matches and " in " in line:
            counts: dict[str, int] = {}
            for match in matches:
                name = match.group("name")
                if name == "error":
                    name = "errors"
                counts[name] = int(match.group("count"))
            return counts
    return {}


def _run_stage(
    name: str,
    command: list[str],
    *,
    accept_no_tests: bool = False,
) -> StageResult:
    print(f"\n=== {name} ===", flush=True)
    print(subprocess.list2cmdline(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
    )
    assert process.stdout is not None
    lines: list[str] = []
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return_code = process.wait()
    return StageResult(
        name=name,
        return_code=return_code,
        counts=_parse_counts("".join(lines)),
        no_tests_accepted=accept_no_tests and return_code == 5,
    )


def _describe(result: StageResult) -> str:
    if result.no_tests_accepted:
        status = "passed (no selected tests)"
    else:
        status = "passed" if result.succeeded else "failed"
    counts = ", ".join(
        f"{count} {name}" for name, count in sorted(result.counts.items())
    )
    detail = counts or "counts unavailable"
    return (
        f"{result.name}: {status}, pytest exit {result.return_code}, "
        f"{detail}, executed {result.executed}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run parallel-safe tests, then timing-sensitive tests serially.",
        allow_abbrev=False,
    )
    parser.add_argument("-n", "--workers", type=int, default=4)
    parser.add_argument("--basetemp", required=True)
    arguments, pytest_arguments = parser.parse_known_args()
    if arguments.workers < 1:
        parser.error("workers must be at least 1")

    basetemp = Path(arguments.basetemp)
    if not basetemp.is_absolute():
        basetemp = ROOT / basetemp
    basetemp.mkdir(parents=True, exist_ok=True)

    common = [str(PYTHON), "-m", "pytest"]
    parallel = _run_stage(
        "parallel-safe",
        [
            *common,
            "-m",
            "not timing_sensitive",
            "-n",
            str(arguments.workers),
            f"--basetemp={basetemp / 'parallel-safe'}",
            *pytest_arguments,
        ],
        accept_no_tests=True,
    )
    timing = _run_stage(
        "timing-sensitive",
        [
            *common,
            "-m",
            "timing_sensitive",
            "-p",
            "no:xdist",
            f"--basetemp={basetemp / 'timing-sensitive'}",
            *pytest_arguments,
        ],
        accept_no_tests=True,
    )

    print("\n=== summary ===", flush=True)
    print(_describe(parallel), flush=True)
    print(_describe(timing), flush=True)
    print(f"total executed: {parallel.executed + timing.executed}", flush=True)
    return 0 if parallel.succeeded and timing.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
