"""Inspect deployment files and stub orchestration; never invoke Docker."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest
import yaml

from scripts.beta_admin import next_reset

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/beta"
spec = importlib.util.spec_from_file_location("beta_host", DEPLOY / "host.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


def compose():
    return yaml.safe_load((DEPLOY / "compose.yml").read_text(encoding="utf-8"))


def test_no_published_internal_ports():
    config = compose()
    for name in ("db", "api", "tools"):
        assert not config["services"][name].get("ports"), name
        assert config["services"][name].get("network_mode") != "host"
    assert config["networks"]["database"]["internal"] is True
    members = {name for name, svc in config["services"].items() if "database" in svc["networks"]}
    assert members == {"db", "api", "tools"}
    assert set(config["services"]["web"]["ports"]) == {"80:80", "443:443"}


def test_api_runtime_confinement():
    api = compose()["services"]["api"]
    assert api["read_only"] is True
    assert api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert api["tmpfs"] and api["mem_limit"]
    assert all(volume.endswith(":ro") for volume in api["volumes"] if ":/beta/contacts:" not in volume)
    assert api["environment"]["DEM_BETA_CONTACT_DIR"] == "/beta/contacts"
    assert any(volume.endswith(":/beta/contacts:rw") for volume in api["volumes"])
    assert "DEM_BETA_SLACK_WEBHOOK_URL" not in api["environment"]
    assert "env_file" not in api
    assert api["environment"]["DEM_BETA"] == "1"
    assert "dem_beta_app:" in api["environment"]["DEM_DATABASE_URL"]
    assert api["environment"]["DEM_DATABASE_URL"].endswith("@db/dem_beta_live")
    assert "/health/ready" in str(api["healthcheck"])


def test_only_web_has_external_network():
    config = compose()
    for name in ("api", "db", "tools"):
        for network in config["services"][name]["networks"]:
            assert config["networks"][network].get("internal") is True, (name, network)
    proxy_members = {name for name, svc in config["services"].items() if "proxy" in svc["networks"]}
    assert proxy_members == {"web", "api"}
    assert config["networks"]["proxy"]["internal"] is True
    assert config["services"]["web"]["networks"]["frontend"] == {}
    assert config["networks"]["frontend"]["internal"] is False


def test_versions_volumes_profiles_and_logging():
    config = compose()
    assert config["services"]["db"]["image"] == "postgres:18.6"
    assert config["services"]["db"]["volumes"] == ["pgdata:/var/lib/postgresql"]
    for name, svc in config["services"].items():
        assert svc["logging"] == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "5"}}
        if name == "tools":
            assert "restart" not in svc
            assert svc["profiles"] == ["tools"]
            assert svc["entrypoint"] == ["python", "-m", "scripts.beta_admin"]
            assert "docker.sock" not in str(svc)
            assert svc["image"] == config["services"]["api"]["image"]
        else:
            assert svc["restart"] == "unless-stopped"
        assert svc["image"] == "postgres:18.6" or svc["image"].endswith(":${DEM_BETA_COMMIT:?set full commit}}")
    api = (DEPLOY / "api.Dockerfile").read_text()
    web = (DEPLOY / "web.Dockerfile").read_text()
    images = re.findall(r"^FROM (\S+)", api + web, re.M)
    assert [image.split("@")[0] for image in images] == ["python:3.13.18-slim-bookworm", "node:22.23.4-alpine", "caddy:2.11.7-builder", "caddy:2.11.7-alpine"]
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", image) for image in images[1:])
    assert all(re.search(r":\d+\.\d+\.\d+", image) for image in images)
    assert "postgresql-client-18" in api and "https://apt.postgresql.org" in api
    assert "USER 10001:10001" in api
    assert "alembic upgrade" not in api
    assert "COPY scripts/beta_admin.py scripts/beta_base.py ./scripts/" in api
    assert "npm ci" in web and "npm run build" in web
    for name in ("api", "web"):
        exclusions = (DEPLOY / f"{name}.Dockerfile.dockerignore").read_text()
        assert exclusions.startswith("**\n")
        assert "**/.env" in exclusions
    assert "!scripts/beta_admin.py" in (DEPLOY / "api.Dockerfile.dockerignore").read_text()


def test_only_fixed_caddy_ip_is_trusted():
    source = (DEPLOY / "api.Dockerfile").read_text()
    command = json.loads(next(line[4:] for line in source.splitlines() if line.startswith("CMD ")))
    def value(flag):
        return command[command.index(flag) + 1]
    ip = value("--forwarded-allow-ips")
    assert ip != "*"
    assert ip == compose()["services"]["web"]["networks"]["proxy"]["ipv4_address"]
    assert value("--workers") == "1"
    assert value("--loop") == "asyncio"
    assert "--proxy-headers" in command
    from webapi.beta import Limits, PROXY_IDLE_CONNECTION_BUDGET, INTERNAL_CONNECTION_BUDGET
    limits = Limits()
    lower = 2 * (limits.concurrent + limits.source_waiters) + PROXY_IDLE_CONNECTION_BUDGET + INTERNAL_CONNECTION_BUDGET
    assert lower <= int(value("--limit-concurrency")) <= 128
    assert value("--timeout-keep-alive") == "5"


def test_runtime_lock_matches_test_environment():
    """Off target, wheel authenticity is checked in the deployment environment (CI)."""
    generator_spec = importlib.util.spec_from_file_location("beta_lock", DEPLOY / "lock_requirements.py")
    generator = importlib.util.module_from_spec(generator_spec)
    generator_spec.loader.exec_module(generator)
    lines = (DEPLOY / "requirements.lock").read_text().splitlines()
    assert all(re.fullmatch(r"[a-z0-9-]+==[^=\s]+", line) for line in lines)
    pinned = dict(line.split("==") for line in lines)
    assert len(pinned) == len(lines)
    checked = generator.verify_runtime_lock()
    assert pinned == checked["versions"]
    assert {"fastapi", "starlette", "psycopg", "psycopg-binary", "httptools", "uvloop"} <= pinned.keys()
    assert not {"pytest", "pytest-xdist", "pytest-postgresql", "filelock", "colorama", "tzdata"} & pinned.keys()
    assert f"FROM {generator.TARGET_BASE_IMAGE}\n" == (DEPLOY / "api.Dockerfile").read_text().splitlines()[0] + "\n"


def test_docker_installs_only_locked_runtime():
    source = (DEPLOY / "api.Dockerfile").read_text()
    assert "COPY deploy/beta/requirements.lock ./requirements.lock" in source
    assert "pip install --no-cache-dir --no-deps -r requirements.lock" in source
    assert "pip install --no-cache-dir --no-deps ." in source
    assert '".[webapi]"' not in source
    assert "!deploy/beta/requirements.lock" in (DEPLOY / "api.Dockerfile.dockerignore").read_text()


def test_env_example_contains_only_placeholders():
    source = (DEPLOY / ".env.example").read_text()
    names = set()
    for line in source.splitlines():
        if not line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        names.add(name)
        assert re.fullmatch(r"'?<[^<>]+>'?", value), name
    needed = set(re.findall(r"\$\{(DEM_BETA_\w+)[:}]", (DEPLOY / "compose.yml").read_text()))
    assert needed <= names
    assert {"DEM_BETA_INTERFACE", "DEM_BETA_MONTHLY_TX_LIMIT"} <= names


def test_caddy_limits_policy_and_logs():
    source = (DEPLOY / "Caddyfile").read_text()
    for clause in ("max_size 262144", "read_header 10s", "read_body 30s", "idle 60s",
                   "response_header_timeout 30s", "uri strip_prefix /api", "@api path /api /api/*",
                   "Strict-Transport-Security", "X-Content-Type-Options nosniff", "Referrer-Policy",
                   "Permissions-Policy", "format json", "roll_size 10MiB", "roll_keep_for 720h",
                   "DEM_BETA_NOINDEX:1", "X-Robots-Tag noindex", "Disallow: /",
                   "max-age=31536000, immutable", "no-cache, no-store", "[502, 503]"):
        assert clause in source, clause
    policy = re.search(r'Content-Security-Policy "([^"]+)"', source)[1]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";"))
    assert directives == {"default-src": "'self'", "script-src": "'self'", "style-src": "'self' 'unsafe-inline'",
                          "font-src": "'self'", "img-src": "'self' data:", "connect-src": "'self'",
                          "frame-ancestors": "'none'", "base-uri": "'none'", "form-action": "'self'", "object-src": "'none'"}
    assert "daily" in (DEPLOY / "install.sh").read_text()
    assert "maxage 30" in (DEPLOY / "install.sh").read_text()
    maintenance = (DEPLOY / "maintenance.html").read_text(encoding="utf-8")
    assert 'lang="ja"' in maintenance and 'lang="en"' in maintenance


def test_caddy_preserves_api_errors_and_only_encodes_static():
    source = (DEPLOY / "Caddyfile").read_text()
    api = source.split("    handle @api {", 1)[1].split("    handle /assets/*", 1)[0]
    assert "handle_response" not in api
    assert "encode" not in api
    assert "handle_errors" in source and "[502, 503]" in source
    assert source.count("encode zstd gzip") == 2
    assert "encode zstd gzip" in source.split("    handle /assets/* {", 1)[1]
    assert "encode zstd gzip" in source.split("    handle {", 1)[1]


@pytest.mark.parametrize("schedule", ["Mon 04:00 Asia/Tokyo", "Fri 23:17 UTC", "Tue 12:05 Europe/London"])
def test_timer_matches_next_reset(schedule, tmp_path):
    host.install_units(DEPLOY / "systemd", tmp_path, schedule)
    rendered = (tmp_path / "dem-beta-reset.timer").read_text()
    calendar = re.search(r"^OnCalendar=(.+)$", rendered, re.M)[1]
    weekday, _, clock, zone = calendar.split()
    beta_schedule = f"{weekday} {clock[:5]} {zone}"
    for now in [datetime(2026, 10, 22, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc)]:
        assert next_reset(now, beta_schedule) == next_reset(now, schedule)
    backup = re.search(r"^OnCalendar=(.+)$", (tmp_path / "dem-beta-backup.timer").read_text(), re.M)[1]
    assert int(backup.split()[1][:2]) == (int(clock[:2]) + 2) % 24
    assert backup.split()[1][3:5] == clock[3:5]


def test_shell_syntax():
    assert BASH, "bash is required for this check"
    for path in (DEPLOY / "install.sh", DEPLOY / "bin/dem-beta"):
        subprocess.run([BASH, "-n", path.as_posix()], check=True, capture_output=True)


def test_traffic_accounts_for_reboots_resets_month_and_interface():
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    state = host.accumulate({}, now, 100, "boot1", "eth0")
    state = host.accumulate(state, now, 150, "boot1", "eth0")
    assert state["total"] == 150
    state = host.accumulate(state, now, 20, "boot2", "eth0")
    assert state["total"] == 170
    state = host.accumulate(state, now, 2, "boot2", "eth0")
    assert state["total"] == 172
    state = host.accumulate(state, now, 10, "boot2", "ens5")
    assert state["total"] == 182
    state = host.accumulate(state, datetime(2026, 11, 1, tzinfo=timezone.utc), 25, "boot2", "ens5")
    assert state["total"] == 15
    with pytest.raises(ValueError, match="traffic state"):
        host.accumulate(dict(state, total=-1), now, 30, "boot2", "ens5")


def test_backup_pruning_preserves_newest_and_unrelated_files(tmp_path):
    for kind in ("backup", "preswap"):
        for day in (1, 2, 3):
            (tmp_path / f"dem-beta-{kind}-202610{day:02}T040000000000Z-abcdef01.dump").touch()
    unrelated = tmp_path / "unrelated.dump"
    unrelated.touch()
    (tmp_path / "dem-beta-backup-20261004T040000000000Z-abcdef01.dump").mkdir()
    assert host.prune_backups(tmp_path) == 4
    assert unrelated.exists()
    assert len(list(tmp_path.glob("*03T*.dump"))) == 2


@pytest.fixture
def shell_host(tmp_path):
    repo = tmp_path / "repo"
    envdir = repo / "deploy/beta"
    envdir.mkdir(parents=True)
    home = tmp_path / "home"
    for name in ("flags", "host-state", "status"):
        (home / name).mkdir(parents=True)
    (envdir / ".env").write_text(f"DEM_BETA_HOME='{home.as_posix()}'\nDEM_BETA_COMMIT={'a'*40}\n")
    binpath = tmp_path / "bin"
    binpath.mkdir()
    # Both programs below are stubs. Docker is never executed by these tests.
    (binpath / "flock").write_text("#!/bin/bash\nexit 0\n")
    (binpath / "python3").write_text('''#!/bin/bash
if [[ "$1" == */notify.py ]]; then
    echo "$*" >> "$TEST_NOTIFY_LOG"
    exit "${FAIL_NOTIFY:-0}"
fi
[[ "$FAIL_STATS" != 1 ]] || exit 1
printf "%s\\n" "$TEST_STATS"
''')
    (binpath / "docker").write_text('''#!/bin/bash
echo "$*" >> "$TEST_LOG"
if [[ "$*" == *"run --rm"*"tools reset prepare"* ]]; then
    echo token > "$DEM_BETA_HOME/flags/read_only"
fi
if [[ -n "$FAIL_AT" && "$*" == *"$FAIL_AT"* ]]; then
    if [[ "$FAIL_AT" == "reset prepare" ]]; then rm -f "$DEM_BETA_HOME/flags/read_only"; fi
    exit 1
fi
if [[ "$1" == inspect ]]; then echo healthy; fi
if [[ "$*" == *"ps -aq api"* ]]; then echo fake-id; fi
if [[ "$*" == *"reset finish"* ]]; then rm -f "$DEM_BETA_HOME/flags/read_only"; fi
''')
    for path in binpath.iterdir():
        path.chmod(0o755)
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env.update(DEM_BETA_REPO=repo.as_posix(), TEST_LOG=(tmp_path / "calls").as_posix(),
               TEST_NOTIFY_LOG=(tmp_path / "notify-calls").as_posix(), DEM_BETA_INTERFACE="eth0", FAIL_AT="", FAIL_STATS="0", TEST_STATS="84 100 0")
    # Git Bash recognizes POSIX path lists, while subprocess needs Windows PATH.
    prefix = binpath.as_posix()
    if os.name == "nt":
        prefix = "/" + prefix[0].lower() + prefix[2:]
    env["BASH_ENV"] = str(tmp_path / "bash-env")
    Path(env["BASH_ENV"]).write_text(f'export PATH="{prefix}:$PATH"\n')
    return tmp_path, home, env


@pytest.mark.parametrize("failure", ["stop api", "reset swap", "start api", "inspect", "reset finish"])
def test_reset_failure_restarts_api_and_keeps_stop_flag(shell_host, failure):
    directory, home, env = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "reset"],
                            env=dict(env, FAIL_AT=failure), capture_output=True, timeout=20)
    assert result.returncode != 0
    assert (home / "flags/read_only").exists()
    calls = (directory / "calls").read_text()
    assert "start api" in calls
    error = json.loads((home / "status/reset-error.json").read_text())
    assert error["stage"] == {"stop api": "stop", "reset swap": "swap", "start api": "start", "inspect": "ready", "reset finish": "finish"}[failure]
    assert set(error) == {"stage", "failed_at"}
    assert datetime.fromisoformat(error["failed_at"].replace("Z", "+00:00")).tzinfo


def test_prepare_failure_leaves_live_running_and_records_error(shell_host):
    directory, home, env = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "reset"],
                            env=dict(env, FAIL_AT="reset prepare"), capture_output=True, timeout=20)
    assert result.returncode != 0
    assert not (home / "flags/read_only").exists()
    calls = (directory / "calls").read_text()
    assert "stop api" not in calls and "start api" not in calls and "reset swap" not in calls
    error = json.loads((home / "status/reset-error.json").read_text())
    assert error["stage"] == "prepare"
    assert set(error) == {"stage", "failed_at"}


def test_reset_success_order_and_finish_after_health(shell_host):
    directory, home, env = shell_host
    error = home / "status/reset-error.json"
    error.write_text('{"stage":"prepare","failed_at":"2026-10-22T00:00:00Z"}')
    subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "reset"], env=env, check=True, capture_output=True, timeout=20)
    calls = (directory / "calls").read_text()
    ordered = ["reset prepare", "stop api", "reset swap", "start api", "inspect", "reset finish"]
    assert [calls.index(part) for part in ordered] == sorted(calls.index(part) for part in ordered)
    assert not (home / "flags/read_only").exists()
    assert not error.exists()


def test_restore_stops_api_before_tool_and_freezes_on_failure(shell_host):
    directory, home, env = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "restore", "backup.dump"],
                            env=dict(env, FAIL_AT="tools restore"), capture_output=True, timeout=20)
    assert result.returncode != 0
    calls = (directory / "calls").read_text()
    assert calls.index("stop api") < calls.index("tools restore") < calls.index("start api")
    assert (home / "flags/read_only").exists()


@pytest.mark.parametrize("stats,failure,frozen,stopped", [
    ("84 100 0", False, False, False),
    ("85 100 0", False, True, False),
    ("90 100 4", False, True, False),
    ("84 2500000000000 0", False, False, True),
    ("", True, True, True),
])
def test_watch_thresholds_and_counter_failure(shell_host, stats, failure, frozen, stopped):
    directory, home, env = shell_host
    result = subprocess.run([BASH, (DEPLOY / "bin/dem-beta").as_posix(), "watch"],
                            env=dict(env, TEST_STATS=stats, FAIL_STATS=str(int(failure))), capture_output=True, timeout=20)
    assert (result.returncode != 0) == failure
    assert (home / "flags/read_only").exists() == frozen
    calls = (directory / "calls").read_text() if (directory / "calls").exists() else ""
    assert ("stop web" in calls) == stopped


def test_web_security_build_gates():
    source = (DEPLOY / "web.Dockerfile").read_text()
    assert "ENV GOTOOLCHAIN=local" in source
    assert "xcaddy build v2.11.7 --replace golang.org/x/net=golang.org/x/net@v0.62.0 --output /usr/bin/caddy" in source
    assert "--with" not in source
    assert "go version -m /usr/bin/caddy" in source and "caddy build-info" in source
    assert "verify-web-security go" in source
    assert "COPY --from=caddy-build /usr/bin/caddy /usr/bin/caddy" in source
    assert "verify-web-security ca /etc/ssl/certs/ca-certificates.crt" in source
    for name in ["ca-certificates", "ca-certificates-bundle"]:
        assert f"'{name}>=20261020-r0'" in source
        assert f"apk info -v {name}" in source
    assert "!deploy/beta/verify-web-security.sh" in (DEPLOY / "web.Dockerfile.dockerignore").read_text()
    assert "pip==26.2.2" in (DEPLOY / "api.Dockerfile").read_text()


@pytest.mark.parametrize("version,accepted", [
    ("1.25.13", False), ("1.26.9", False), ("1.26.10", True),
    ("1.27.2", False), ("1.27.3", True), ("1.28.0", True),
    ("", False), ("devel", False), ("1.28.", False), ("1.27.3rc1", False),
])
def test_go_toolchain_security_floor(version, accepted):
    result = subprocess.run([BASH, str(DEPLOY / "verify-web-security.sh"), "go", version], capture_output=True)
    assert (result.returncode == 0) is accepted, result.stderr


@pytest.mark.parametrize("subject,accepted", [("DEM unit test root", True), ("emSign ECC Root CA - G3", False)])
def test_ca_bundle_inspects_certificate_subjects(tmp_path, subject, accepted):
    # Real PEM certificates with no readable name comments in the bundle.
    bundle, key = tmp_path / "ca.pem", tmp_path / "key.pem"
    subprocess.run([BASH, "-c", 'openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1 -subj "$1" -keyout "$2" -out "$3"',
                    "_", "/CN=" + subject, str(key), str(bundle)], check=True, capture_output=True, env=dict(os.environ, MSYS2_ARG_CONV_EXCL="*"))
    assert subject not in bundle.read_text()
    result = subprocess.run([BASH, str(DEPLOY / "verify-web-security.sh"), "ca", str(bundle)], capture_output=True)
    assert (result.returncode == 0) is accepted, result.stderr


def test_ca_bundle_parse_failure_is_rejected(tmp_path):
    bundle = tmp_path / "invalid.pem"
    bundle.write_text("not a certificate")
    result = subprocess.run([BASH, str(DEPLOY / "verify-web-security.sh"), "ca", str(bundle)], capture_output=True)
    assert result.returncode != 0


# Go 1.27.3 BuildInfo.String omits the original checksum when replaced.
# Parse both legitimate 3-field and 4-field rows; the version is mandatory.
_BUILD_HEADER = "/usr/bin/caddy: go1.27.3\n\tpath\tcommand-line-arguments\n"
_CADDY_DEP = "\tdep\tgithub.com/caddyserver/caddy/v2\tv2.11.7\th1:test\n"


def _net_dep(version):
    return f"\tdep\tgolang.org/x/net\t{version}\th1:test\n"


def _net_replacement(version, path="golang.org/x/net"):
    return f"\t=>\t{path}\t{version}\th1:test\n"


@pytest.mark.parametrize("rows,accepted", [
    (_net_dep("v0.59.0"), False),
    (_net_dep("v0.62.0") + _net_replacement("v0.59.0"), False),
    ("", False),
    (_net_dep("(devel)"), False),
    (_net_dep("v0.60.0-rc"), False),
    (_net_dep("v0.59.0") + _net_replacement("v0.60.0-rc"), False),
    (_net_dep("v0.59.0") + _net_replacement("(devel)"), False),
    (_net_dep("v0.59.0").replace("\th1:test", "") + _net_replacement("v0.62.0"), True),
    (_net_dep("v0.60.0").replace("\th1:test", ""), True),
    (_net_dep("v0.62.0"), True),
    (_net_dep("v1.0.0"), True),
    (_net_dep("v0.62.0") + _net_dep("v0.62.0"), False),
    (_net_dep("v0.59.0") + _net_replacement("v0.62.0", "example.invalid/net"), False),
    (_net_replacement("v0.62.0"), False),
    (_net_dep("v0.59.0") + "\n" + _net_replacement("v0.62.0"), False),
    (_net_dep("v0.62.0") + _net_replacement("v0.62.0") + _net_replacement("v0.62.0"), False),
    (_net_dep("v0.062.0"), False),
    (_net_dep("v0.62.0").replace("\tv0.62.0", ""), False),
    (_net_dep("v0.62.0") + "\tdep\texample.invalid/other\tv0.1.0\th1:test\n" + _net_replacement("v0.59.0", "example.invalid/other"), True),
])
def test_linked_xnet_security_floor(tmp_path, rows, accepted):
    info = tmp_path / "build-info.txt"
    info.write_text(_BUILD_HEADER + _CADDY_DEP + rows)
    result = subprocess.run([BASH, str(DEPLOY / "verify-web-security.sh"), "build-info", str(info), "v2.11.7"], capture_output=True)
    assert (result.returncode == 0) is accepted, result.stderr


@pytest.mark.parametrize("rows", [
    "",
    _CADDY_DEP.replace("v2.11.7", "v2.11.6"),
    _CADDY_DEP + "\t=>\tgithub.com/caddyserver/caddy/v2\tv2.11.6\th1:test\n",
    _CADDY_DEP.replace("v2.11.7", "(devel)"),
    _CADDY_DEP + _CADDY_DEP,
])
def test_build_rejects_wrong_or_ambiguous_caddy(tmp_path, rows):
    info = tmp_path / "build-info.txt"
    info.write_text(_BUILD_HEADER + rows + _net_dep("v0.62.0"))
    result = subprocess.run([BASH, str(DEPLOY / "verify-web-security.sh"), "build-info", str(info), "v2.11.7"], capture_output=True)
    assert result.returncode != 0


def test_linked_module_build_gate_and_sumdb():
    source = (DEPLOY / "web.Dockerfile").read_text()
    assert source.count("--replace ") == 1
    assert "--replace golang.org/x/net=golang.org/x/net@v0.62.0" in source
    assert "verify-web-security build-info /tmp/caddy-build-info v2.11.7" in source
    assert "GOSUMDB=sum.golang.org" in source
    assert "GOPROXY=https://proxy.golang.org" in source
    assert not re.search(r"(?:GONOSUMDB|GONOSUMCHECK|GOINSECURE|GOPRIVATE|GOFLAGS)\s*=", source)


def test_patched_runtime_packages_and_openssl_removal():
    source = (DEPLOY / "web.Dockerfile").read_text()
    for name, minimum in [("curl", "8.23.0-r0"), ("libcurl", "8.23.0-r0"), ("brotli-libs", "1.2.1-r0")]:
        assert f"'{name}>={minimum}'" in source
        assert f"apk info -v {name} |" in source
        assert re.search(r"apk version -t[^\n]+" + re.escape(minimum), source)
    assert " libssl3 libcrypto3 openssl" in source
    assert source.index("verify-web-security ca /etc/ssl/certs/ca-certificates.crt") < source.index("apk del --no-cache openssl") < source.index("&& caddy version")
    assert "! apk info -e openssl" in source and "! command -v openssl" in source
    for library in ["libssl3", "libcrypto3"]:
        assert f"apk info -e {library}" in source
    assert "apk del --no-cache curl" not in source


def test_beta_only_advertises_published_tcp_http_protocols():
    root = Path(__file__).resolve().parents[1]
    config = (root / 'deploy/beta/Caddyfile').read_text()
    compose = (root / 'deploy/beta/compose.yml').read_text()
    assert 'protocols h1 h2' in config
    assert '443:443/udp' not in compose and 'protocol: udp' not in compose
