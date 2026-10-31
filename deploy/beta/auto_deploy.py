"""Root-only pull deployment. No candidate code runs before object verification.

Preparation uses a separate Compose project, PostgreSQL volume and runtime home.
The installed wrapper is the only entry point; all subprocess output is private.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from zoneinfo import ZoneInfo

UTC = timezone.utc
SHA = re.compile(r"[0-9a-f]{40}\Z")
TAG = re.compile(r"beta-[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
GRACE = 300  # Persistent timer catch-up: at most five minutes, never early.


class Rejected(Exception):
    pass


class Busy(Rejected):
    pass


class Early(Rejected):
    pass


class RecoveryRequired(Rejected):
    pass


def run(args, *, cwd=None, env=None, timeout=120):
    # Do not include stderr, command arguments, env or exception text in reports.
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise Rejected("command failed")
    return result.stdout.decode("utf-8").strip()


def atomic(path, content):
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        os.chmod(temporary, 0o600)
        output.write(content.encode())
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def save(path, value):
    atomic(path, json.dumps(value, sort_keys=True) + "\n")


def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_size > 16384:
        raise Rejected("unsafe deployment record")
    return json.loads(path.read_text())


@contextmanager
def lock(path, *, blocking=False):
    import fcntl
    with path.open("a") as output:
        try:
            fcntl.flock(output, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise Busy("busy") from None
        yield


@contextmanager
def checkout_permissions():
    # Only public checkout data is readable by image UID 10001. Secrets and the
    # enclosing release/runtime retain the wrapper's restrictive umask.
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def instant(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise Rejected("timezone required")
    return date.astimezone(UTC)


def approval(tag, commit, tree, at, schedule, now):
    if not TAG.fullmatch(tag) or not SHA.fullmatch(commit) or not SHA.fullmatch(tree):
        raise Rejected("invalid approval")
    date = instant(at)
    match = re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([0-2]\d):([0-5]\d) (\S+)", schedule)
    if not match or int(match[2]) > 23:
        raise Rejected("invalid schedule")
    local = date.astimezone(ZoneInfo(match[4]))
    if (f"{'Mon Tue Wed Thu Fri Sat Sun'.split()[local.weekday()]} {local:%H:%M}" != f"{match[1]} {match[2]}:{match[3]}"
            or local.second or local.microsecond or date <= now or date > now + timedelta(days=7)):
        raise Rejected("approval must name the upcoming reset")
    return dict(tag=tag, commit=commit, tree=tree, at=date.isoformat())


def due(record, now):
    return 0 <= (now - instant(record["at"])).total_seconds() <= GRACE


def verify(repo, objects, record, baseline):
    remote = run(["git", "-C", repo, "remote", "get-url", "origin"])
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", remote):
        raise Rejected("public HTTPS origin required")
    run(["git", "init", "--bare", objects])
    run(["git", "-C", objects, "fetch", "--no-tags", remote, f"refs/tags/{record['tag']}", baseline], timeout=180)
    commit = run(["git", "-C", objects, "rev-parse", "FETCH_HEAD^{commit}"])
    # FETCH_HEAD is first ref fetched; resolve it before any other fetch.
    tree = run(["git", "-C", objects, "rev-parse", f"{commit}^{{tree}}"])
    if (commit, tree) != (record["commit"], record["tree"]):
        raise Rejected("approval mismatch")
    changed = run(["git", "-C", objects, "diff", "--name-only", baseline, commit, "--", "deploy/beta"])
    if changed:
        raise Rejected("host files changed; manual host update required")
    return commit


class Deployment:
    def __init__(self, repo):
        self.repo = Path(repo)
        self.env = dict(os.environ)
        self.home = Path(self.env["DEM_BETA_HOME"])
        self.state = self.home / "host-state"
        self.baseline = self.env["DEM_BETA_HOST_COMMIT"]
        self.now = lambda: datetime.now(UTC)
        self.switch_started = False
        self.stage = "prepare"

    def event(self, outcome):
        # A single fixed vocabulary record enters the existing deduplicated spool.
        save(self.state / "deploy-event.json", dict(at=self.now().isoformat(), outcome=outcome))

    def dc(self, repo, env, *args):
        return run(["docker", "compose", "--project-name", "dem-beta", "--env-file", Path(repo) / "deploy/beta/.env",
                    "-f", Path(repo) / "deploy/beta/compose.yml", *args], env=env, timeout=2400)

    def tools(self, repo, env, *args):
        return self.dc(repo, env, "run", "--rm", "-T", "tools", *args)

    def check_baseline(self):
        if not SHA.fullmatch(self.baseline):
            raise Rejected("invalid host commit")
        if run(["git", "-C", self.repo, "rev-parse", "HEAD"]) != self.baseline:
            raise Rejected("active commit mismatch")
        if run(["git", "-C", self.repo, "status", "--porcelain", "--untracked-files=no"]):
            raise Rejected("active checkout modified")

    def plan(self, record):
        self.check_baseline()
        with tempfile.TemporaryDirectory() as temporary:
            verify(self.repo, Path(temporary) / "objects", record, self.baseline)
        return dict(**record, baseline=self.baseline, live_image_commit=self.env["DEM_BETA_COMMIT"], plan="isolated build/base; one scheduled reset; no rollback")

    def env_file(self, repo, env):
        # A common literal subset for bash source AND Compose dotenv. Reject
        # quoting/expansion characters rather than applying shell-only escaping.
        keys = [key for key in env if key.startswith("DEM_BETA_") or key == "COMPOSE_PROJECT_NAME"]
        for key in keys:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or not re.fullmatch(r"[A-Za-z0-9_./:@%+=, ?&-]*", env[key]):
                raise Rejected("unsupported environment characters")
        atomic(repo / "deploy/beta/.env", "".join(f"{key}='{env[key]}'\n" for key in sorted(keys)))

    def pc(self, repo, env, *args):
        return run(["docker", "compose", "--project-name", env["COMPOSE_PROJECT_NAME"],
                    "--env-file", Path(repo) / "deploy/beta/.env",
                    "-f", Path(repo) / "deploy/beta/prepare.compose.yml", *args], env=env, timeout=2400)

    def discard(self, path):
        try:
            path.unlink(missing_ok=True)
        except FileNotFoundError:
            self.event("pre-switch-rejected")  # Concurrent consumption; still reset.

    def consume_records(self):
        for name in ("deploy-approval.json", "deploy-prepared.json", "deploy-consumed.json"):
            self.discard(self.state / name)

    def check_candidate(self, record):
        identifier = record["id"]
        if (not re.fullmatch(r"[0-9a-f]{40}-[0-9]{10,30}", identifier)
                or record["commit"] != identifier.split("-", 1)[0]
                or record["volume"] != "dem-beta-db-" + identifier
                or record["project"] != "dem-beta-prepare-" + identifier
                or Path(record["repo"]) != self.home / "releases" / identifier / "repo"
                or Path(record["runtime"]) != self.home / "releases" / identifier / "runtime"):
            raise Rejected("invalid candidate identity")

    def stop_candidate(self, record):
        # Only root-registered preparation projects. Never target the stable live
        # project, and never remove volumes (including the selected DB volume).
        self.check_candidate(record)
        identifier = record["id"]
        project = "dem-beta-prepare-" + identifier
        ids = run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project,
                   "--format", "{{.ID}}"], env=self.env).split()
        if any(not re.fullmatch(r"[0-9a-f]{12,64}", value) for value in ids):
            raise Rejected("invalid container identity")
        if ids:
            run(["docker", "stop", "--time", "30", *ids], env=self.env)
            run(["docker", "rm", *ids], env=self.env)
        networks = run(["docker", "network", "ls", "--filter", "label=com.docker.compose.project=" + project,
                        "--format", "{{.ID}}"], env=self.env).split()
        if any(not re.fullmatch(r"[0-9a-f]{12,64}", value) for value in networks):
            raise Rejected("invalid network identity")
        for network in networks:
            run(["docker", "network", "rm", network], env=self.env)

    def cleanup_candidates(self):
        directory = self.state / "deploy-candidates"
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                record = read(path)
                if record["id"] != path.stem:
                    raise Rejected("candidate registry mismatch")
                self.stop_candidate(record)
            except Exception:
                # Keep the registry for retry; do not silently skip a reset.
                self.event("cleanup-failed")

    def preparing(self, record):
        if self.now() >= instant(record["at"]) or (self.state / "deploy-cancelled").exists():
            raise Rejected("preparation expired or cancelled")

    def prepare(self):
        # Caller holds deploy.lock: an earlier preparation is no longer running.
        self.cleanup_candidates()
        path = self.state / "deploy-approval.json"
        if not path.exists() and not path.is_symlink():
            return
        try:
            record = read(path)
            remaining = (instant(record["at"]) - self.now()).total_seconds()
        except Exception:
            self.discard(path)
            self.event("preparation-failed")
            return
        if remaining > 3600:
            return
        self.discard(path)
        save(self.state / "deploy-consumed.json", record)
        self.event("preparing")
        candidate = None
        try:
            self.preparing(record)
            self.check_baseline()
            identifier = record["commit"] + "-" + str(time.time_ns())
            release = self.home / "releases" / identifier
            release.mkdir(parents=True, mode=0o700)
            repo, objects = release / "repo", release / "objects"
            verify(self.repo, objects, record, self.baseline)
            with checkout_permissions():
                run(["git", "clone", "--no-checkout", objects, repo])
                run(["git", "-C", repo, "checkout", "--detach", record["commit"]])
            remote = run(["git", "-C", self.repo, "remote", "get-url", "origin"])
            run(["git", "-C", repo, "remote", "set-url", "origin", remote])
            isolated = release / "runtime"
            for name in ("flags", "status", "state", "backups", "contacts", "logs"):
                directory = isolated / name
                directory.mkdir(parents=True, mode=0o755)
                os.chown(directory, 10001, 10001)
            candidate = dict(**record, id=identifier, repo=str(repo), baseline=self.baseline,
                             project="dem-beta-prepare-" + identifier, runtime=str(isolated),
                             volume="dem-beta-db-" + identifier)
            registry = self.state / "deploy-candidates"
            registry.mkdir(mode=0o700, exist_ok=True)
            # Publish ownership BEFORE any Docker resource is created: even a
            # SIGKILL leaves enough trusted identity for the next timer to reap.
            save(registry / (identifier + ".json"), candidate)
            env = dict(self.env, DEM_BETA_HOME=isolated.as_posix(), DEM_BETA_COMMIT=record["commit"],
                       DEM_BETA_DB_VOLUME=candidate["volume"], COMPOSE_PROJECT_NAME=candidate["project"])
            self.env_file(repo, env)
            self.preparing(record)
            candidate["images"] = {}
            for service in ("api", "web"):
                tag = f"dem-beta-{service}:candidate-{identifier}"
                run(["docker", "build", "-t", tag,
                     "-f", repo / f"deploy/beta/{service}.Dockerfile", repo], env=env, timeout=2400)
                image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], env=env)
                if not IMAGE_ID.fullmatch(image_id):
                    raise Rejected("invalid prepared image ID")
                candidate["images"][service] = image_id
                env["DEM_BETA_" + service.upper() + "_IMAGE"] = image_id
                self.preparing(record)
            save(registry / (identifier + ".json"), candidate)
            self.env_file(repo, env)
            # Read every application source as the real image UID; no DB, secret
            # environment, ports or network. Failure is preparation failure.
            probe = ("import os\nfrom pathlib import Path\n"
                     "assert os.getuid() == 10001\n"
                     "import dem, demlang, scripts.beta_admin, webapi\n"
                     "def denied(error): raise error\n"
                     "for directory, folders, files in os.walk('/app', onerror=denied):\n"
                     " for name in files: Path(directory, name).read_bytes()\n")
            run(["docker", "run", "--rm", "--user", "10001:10001", "--network", "none",
                 "--label", "com.docker.compose.project=" + candidate["project"],
                 "--entrypoint", "python", candidate["images"]["api"], "-c", probe], env=env)
            self.preparing(record)
            # Never create a proxy network or mount live certificate volumes.
            run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "caddy",
                 "--tmpfs", "/var/log/caddy", "--label", "com.docker.compose.project=" + candidate["project"], "-e", "DEM_BETA_DOMAIN=" + env["DEM_BETA_DOMAIN"],
                 "-e", "DEM_BETA_NOINDEX=" + env.get("DEM_BETA_NOINDEX", "1"),
                 candidate["images"]["web"], "validate", "--config", "/etc/caddy/Caddyfile",
                 "--adapter", "caddyfile"], env=env)
            self.preparing(record)
            run(["docker", "volume", "create", "--label", "dem.beta.deployment=" + identifier,
                 candidate["volume"]], env=env)
            self.pc(repo, env, "up", "-d", "--wait", "db")
            for command in ("roles", "build-base", "status"):
                self.preparing(record)
                self.pc(repo, env, "run", "--rm", "-T", "tools", command)
            self.stop_candidate(candidate)
            with lock(self.state / "operation.lock"):
                self.preparing(record)
                save(self.state / "deploy-prepared.json", candidate)
                self.event("prepared")
        except Exception:
            # Best-effort now, durable registry guarantees a later timer retry.
            if candidate is not None:
                try:
                    self.stop_candidate(candidate)
                except Exception:
                    self.event("cleanup-failed")
            self.event("cancelled" if (self.state / "deploy-cancelled").exists() else "preparation-failed")

    def freeze(self):
        path = self.home / "flags/read_only"
        if not path.exists():
            path.write_text("host maintenance\n")
            path.chmod(0o644)

    def switching(self):
        save(self.state / "deploy-switching.json", dict(started_at=self.switch_time, stage=self.stage))

    def failed(self):
        self.freeze()
        save(self.home / "status/reset-error.json", dict(failed_at=self.now().isoformat(), stage=self.stage))
        (self.home / "status/reset-error.json").chmod(0o644)
        self.event("switch-failed")
        self.discard(self.state / "deploy-switching.json")

    def critical(self, repo, env, record):
        for service in ("api", "web"):
            container = self.dc(repo, env, "ps", "-aq", service)
            info = json.loads(run(["docker", "inspect", container]))[0]
            expected = record["images"][service]
            if not IMAGE_ID.fullmatch(expected) or info["Config"]["Image"] != expected or info["Image"] != expected:
                raise Rejected("version mismatch")
            if service == "api":
                if f"DEM_BETA_COMMIT={record['commit']}" not in info["Config"]["Env"]:
                    raise Rejected("version mismatch")
                if info["State"].get("Health", {}).get("Status") != "healthy":
                    raise Rejected("unhealthy API")
        health = json.loads(run(["curl", "--fail", "--silent", "--show-error", "--max-time", "15",
                                 f"https://{env['DEM_BETA_DOMAIN']}/api/health/ready"]))
        if health != {"status": "ok"}:
            raise Rejected("unhealthy API")

    def observations(self, env):
        base = f"https://{env['DEM_BETA_DOMAIN']}"
        config = json.loads(run(["curl", "-fsS", "--max-time", "15", base + "/api/config"]))
        expected = json.loads((self.home / "status/status.json").read_text())["next_reset_at"]
        # API config nests beta status under beta.
        if config.get("beta", {}).get("next_reset_at") != expected:
            raise Rejected("next reset mismatch")
        for protocol, version in (("--http2", "2"), ("--http1.1", "1.1")):
            headers = run(["curl", "-fsS", protocol, "--max-time", "15", "-D", "-", "-o", "/dev/null", "-w", "\n%{http_version}", base + "/"])
            lower = headers.lower()
            if headers.splitlines()[-1] != version or "alt-svc:" in lower:
                raise Rejected("protocol check failed")
            for header in ("strict-transport-security: max-age=31536000", "x-content-type-options: nosniff",
                           "referrer-policy: strict-origin-when-cross-origin", "permissions-policy: camera=(), microphone=(), geolocation=()",
                           "content-security-policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'", "cache-control: no-cache, no-store"):
                if header not in lower:
                    raise Rejected("header check failed")
            if env.get("DEM_BETA_NOINDEX", "1") == "1" and "x-robots-tag: noindex" not in lower:
                raise Rejected("noindex check failed")
        for path in ("/", "/theorems", "/symbols", "/terms", "/privacy", "/disclaimer"):
            run(["curl", "-fsS", "--max-time", "15", base + path])

    def switch(self, record):
        self.check_candidate(record)
        repo = Path(record["repo"])
        env = dict(self.env, DEM_BETA_COMMIT=record["commit"], COMPOSE_PROJECT_NAME="dem-beta",
                   DEM_BETA_DB_VOLUME=record["volume"])
        for service in ("api", "web"):
            image_id = record["images"][service]
            if not IMAGE_ID.fullmatch(image_id):
                raise Rejected("invalid prepared image ID")
            env["DEM_BETA_" + service.upper() + "_IMAGE"] = image_id
        self.check_baseline()
        # Recheck object identity and host-file boundary at the last trusted point.
        self.plan(record_for_approval(record))
        if record["baseline"] != self.baseline or not due(record, self.now()):
            raise Rejected("outside approved reset")
        if (self.home / "flags/read_only").exists():
            raise Rejected("already frozen")
        if run(["git", "-C", repo, "rev-parse", "HEAD"]) != record["commit"] or run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"]):
            raise Rejected("prepared checkout changed")
        for image_id in record["images"].values():
            if run(["docker", "image", "inspect", "--format", "{{.Id}}", image_id], env=env) != image_id:
                raise Rejected("prepared image missing or changed")
        # Validate dotenv before stopping anything; env_file writes only the candidate.
        self.env_file(repo, env)
        volume_owner = run(["docker", "volume", "inspect", "--format",
                            '{{index .Labels "dem.beta.deployment"}}', record["volume"]], env=self.env)
        if volume_owner != record["id"]:
            raise Rejected("prepared volume missing or changed")
        self.tools(self.repo, self.env, "backup")
        # No slow operation may allow us to cross the permitted time window.
        if not due(record, self.now()):
            raise Rejected("outside approved reset")
        try:
            self.stage = "stop"
            self.switch_time = self.now().isoformat()
            self.switching()
            self.switch_started = True
            self.freeze()
            self.dc(self.repo, self.env, "stop", "api", "web", "db")
            container = self.dc(self.repo, self.env, "ps", "-aq", "api")
            if run(["docker", "inspect", "--format", "{{.State.Running}}", container]) != "false":
                raise Rejected("old API still running")
            # Prepared DB is stopped before mounting its generation volume in
            # the stable project. Force recreation even if only volume.name changed.
            self.stop_candidate(record)
            atomic(self.home / "state/base.json", (Path(record["runtime"]) / "state/base.json").read_text())
            os.chown(self.home / "state/base.json", 10001, 10001)
            atomic(self.state / "active-repo", str(repo) + "\n")
            self.stage = "start"
            self.switching()
            self.dc(repo, env, "up", "-d", "--no-deps", "--force-recreate", "--wait", "db")
            self.stage = "prepare"
            self.switching()
            (self.home / "flags/read_only").unlink()
            self.tools(repo, env, "reset", "prepare")
            self.stage = "swap"
            self.switching()
            self.tools(repo, env, "reset", "swap")
            self.stage = "start"
            self.switching()
            self.dc(repo, env, "up", "-d", "--no-deps", "--no-build", "--force-recreate", "--wait", "api", "web")
            self.stage = "ready"
            self.switching()
            self.critical(repo, env, record)
            warning = False
            try:
                self.observations(env)
            except Exception:
                warning = True
            self.stage = "finish"
            self.switching()
            self.tools(repo, env, "reset", "finish")
            self.discard(self.state / "deploy-switching.json")
            self.event("deployed-check-warning" if warning else "deployed")
        except Exception:
            self.failed()
            raise


    def fallback(self):
        # Notification/storage failure is not permission to skip the ordinary
        # reset. Attempt every action independently; wrapper still validates DB.
        for action in (self.consume_records, lambda: self.event("pre-switch-rejected"), self.cleanup_candidates):
            try:
                action()
            except Exception:
                print("dem-beta deploy: fallback bookkeeping failed")
        return False

    def scheduled(self):
        if ((self.home / "status/reset-error.json").exists()
                or (self.state / "deploy-switching.json").exists()):
            self.freeze()
            self.event("recovery-blocked")
            self.cleanup_candidates()
            raise RecoveryRequired("manual recovery required")
        try:
            for name in ("deploy-approval.json", "deploy-consumed.json", "deploy-prepared.json"):
                pending = self.state / name
                if (pending.exists() or pending.is_symlink()) and self.now() < instant(read(pending)["at"]):
                    raise Early("reset invoked early")
            self.discard(self.state / "deploy-approval.json")
            path = self.state / "deploy-prepared.json"
            if path.exists() or path.is_symlink():
                record = read(path)
                self.discard(path)
                if due(record, self.now()):
                    self.switch(record)
                    return True
                self.event("approval-expired")
            self.consume_records()
            self.cleanup_candidates()
            return False
        except Early:
            try:
                self.event("early-reset-rejected")
            except Exception:
                print("dem-beta deploy: early-reset notification recording failed")
            raise
        except Exception:
            if (self.switch_started or (self.state / "deploy-switching.json").exists()
                    or (self.home / "status/reset-error.json").exists()):
                raise
            # A malformed record, permission rejection, cleanup error, or an
            # unlink race must never silently suppress the ordinary reset.
            return self.fallback()


def record_for_approval(record):
    return {key: record[key] for key in ("tag", "commit", "tree", "at")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("command", choices=("deploy-approve", "deploy-cancel", "deploy-status", "deploy-dry-run", "deploy-prepare", "scheduled-reset"))
    parser.add_argument("tag", nargs="?")
    parser.add_argument("commit", nargs="?")
    parser.add_argument("tree", nargs="?")
    parser.add_argument("at", nargs="?")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("root required")
    deployment = Deployment(args.repo)
    try:
        # Preparation never holds operation.lock: watch/backup/status use old DB.
        # Reset never waits for preparation; if it is still running, invalidate it
        # through the deadline check and perform the ordinary reset instead.
        if args.command == "scheduled-reset":
            with lock(deployment.state / "operation.lock"):
                try:
                    deployed = deployment.scheduled()
                except (Early, RecoveryRequired):
                    raise
                except Exception:
                    if (deployment.switch_started or (deployment.state / "deploy-switching.json").exists()
                            or (deployment.home / "status/reset-error.json").exists()):
                        raise
                    deployed = deployment.fallback()
            if not deployed:
                run(["/usr/local/sbin/dem-beta", "reset"], env=deployment.env, timeout=1100)
            return 0
        if args.command == "deploy-dry-run":
            if not all((args.tag, args.commit, args.tree, args.at)):
                raise Rejected("tag commit tree reset-UTC required")
            record = approval(args.tag, args.commit, args.tree, args.at,
                              deployment.env["DEM_BETA_RESET_SCHEDULE"], deployment.now())
            print(json.dumps(deployment.plan(record)))
            return 0
        if args.command == "deploy-status":
            print(json.dumps({name: read(deployment.state / name) for name in
                              ("deploy-approval.json", "deploy-prepared.json", "deploy-event.json")
                              if (deployment.state / name).exists()}))
            return 0
        if args.command == "deploy-cancel":
            with lock(deployment.state / "operation.lock"):
                atomic(deployment.state / "deploy-cancelled", "cancelled\n")
                for name in ("deploy-approval.json", "deploy-prepared.json", "deploy-consumed.json"):
                    deployment.discard(deployment.state / name)
                deployment.cleanup_candidates()
                deployment.event("cancelled")
            return 0
        with lock(deployment.state / "deploy.lock"):
            if args.command == "deploy-approve":
                if not all((args.tag, args.commit, args.tree, args.at)):
                    raise Rejected("tag commit tree reset-UTC required")
                record = approval(args.tag, args.commit, args.tree, args.at,
                                  deployment.env["DEM_BETA_RESET_SCHEDULE"], deployment.now())
                plan = deployment.plan(record)
                with lock(deployment.state / "operation.lock"):
                    deployment.check_baseline()
                    if any((deployment.state / name).exists() for name in ("deploy-approval.json", "deploy-prepared.json")):
                        raise Rejected("cancel existing approval first")
                    (deployment.state / "deploy-cancelled").unlink(missing_ok=True)
                    save(deployment.state / "deploy-approval.json", record)
                print(json.dumps(plan))
            else:
                deployment.prepare()
        return 0
    except Exception as exc:
        print("dem-beta deploy: operation rejected or failed; inspect root-only state")
        return 75 if isinstance(exc, Busy) else 1


if __name__ == "__main__":
    raise SystemExit(main())
