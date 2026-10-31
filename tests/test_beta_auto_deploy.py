"""Adversarial host deployment matrix; no Docker, network or external hosts."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("auto_deploy", ROOT / "deploy/beta/auto_deploy.py")
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)
NOW = datetime(2026, 11, 15, 19, tzinfo=timezone.utc)  # Monday 04:00 JST
RECORD = dict(tag="beta-2026-11.15", commit="b" * 40, tree="c" * 40, at=NOW.isoformat())


def test_approval_accepts_exact_upcoming_reset():
    assert auto.approval(**RECORD, schedule="Mon 04:00 Asia/Tokyo", now=NOW-timedelta(hours=12)) == RECORD


@pytest.mark.parametrize("change", [dict(commit="b"*39), dict(tree="x"*40), dict(tag="--upload-pack=evil"),
    dict(tag="beta-../bad"), dict(at="2026-11-16T04:00:00"), dict(at=(NOW-timedelta(seconds=1)).isoformat()),
    dict(at=(NOW+timedelta(minutes=1)).isoformat()), dict(at=(NOW+timedelta(days=7)).isoformat())])
def test_approval_rejects_invalid_input(change):
    with pytest.raises((auto.Rejected, ValueError)):
        auto.approval(**dict(RECORD, **change), schedule="Mon 04:00 Asia/Tokyo", now=NOW-timedelta(hours=1))


@pytest.mark.parametrize("offset,expected", [(-1, False), (0, True), (300, True), (301, False)])
def test_switch_window(offset, expected):
    assert auto.due(RECORD, NOW+timedelta(seconds=offset)) is expected


@pytest.mark.parametrize("mismatch", ["none", "commit", "tree", "host"])
def test_verify_before_candidate_execution(tmp_path, monkeypatch, mismatch):
    calls = []
    def fake(args, **kwargs):
        calls.append(list(map(str, args)))
        text = " ".join(map(str, args))
        if "get-url" in text:
            return "https://github.com/example/demo.git"
        if "FETCH_HEAD^{commit}" in text:
            return "d"*40 if mismatch == "commit" else RECORD["commit"]
        if "^{tree}" in text:
            return "d"*40 if mismatch == "tree" else RECORD["tree"]
        if "diff" in text:
            return "deploy/beta/host.py" if mismatch == "host" else ""
        return ""
    monkeypatch.setattr(auto, "run", fake)
    if mismatch == "none":
        assert auto.verify(tmp_path, tmp_path/"objects", RECORD, "a"*40) == RECORD["commit"]
    else:
        with pytest.raises(auto.Rejected):
            auto.verify(tmp_path, tmp_path/"objects", RECORD, "a"*40)
    assert all(call[0] == "git" for call in calls)
    assert not any("checkout" in call or "clone" in call for call in calls)


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    home, repo = tmp_path / "home", tmp_path / "active"
    for name in ("host-state", "flags", "status", "state"):
        (home / name).mkdir(parents=True)
    (repo / "deploy/beta").mkdir(parents=True)
    (repo / "deploy/beta/.env").write_text("original-env")
    monkeypatch.setenv("DEM_BETA_HOME", str(home))
    monkeypatch.setenv("DEM_BETA_COMMIT", "a"*40)
    monkeypatch.setenv("DEM_BETA_HOST_COMMIT", "a"*40)
    monkeypatch.setenv("DEM_BETA_DOMAIN", "example.invalid")
    monkeypatch.setenv("DEM_BETA_RESET_SCHEDULE", "Mon 04:00 Asia/Tokyo")
    d = auto.Deployment(repo)
    d.env = {key: os.environ[key] for key in ("DEM_BETA_HOME", "DEM_BETA_COMMIT", "DEM_BETA_HOST_COMMIT", "DEM_BETA_DOMAIN", "DEM_BETA_RESET_SCHEDULE")}
    d.env["DEM_BETA_HOME"] = home.as_posix()
    d.now = lambda: NOW-timedelta(minutes=30)
    monkeypatch.setattr(auto, "read", lambda p: json.loads(p.read_text()))
    monkeypatch.setattr(auto, "lock", lambda *a, **k: nullcontext())
    monkeypatch.setattr(auto.os, "chown", lambda *a: None, raising=False)
    monkeypatch.setattr(d, "check_baseline", lambda: None)
    monkeypatch.setattr(d, "plan", lambda r: r)
    monkeypatch.setattr(auto, "verify", lambda *args: RECORD["commit"])
    calls = []
    def execute(args, **kwargs):
        args = list(map(str, args)); calls.append((args, kwargs.get("env")))
        if args[:2] == ["git", "clone"]:
            target = Path(args[-1]); (target / "deploy/beta").mkdir(parents=True)
            (target.parent / "runtime/state").mkdir(parents=True)
            (target.parent / "runtime/state/base.json").write_text('{"verified":true}')
        if "rev-parse" in args:
            return RECORD["commit"]
        if "get-url" in args:
            return "https://github.com/example/demo.git"
        if args[:3] == ["docker", "volume", "inspect"]:
            return args[-1].removeprefix("dem-beta-db-")
        if args[0] == "docker" and "inspect" in args:
            return "false"
        return ""
    monkeypatch.setattr(auto, "run", execute)
    # Let prepare create its runtime directory itself.
    original_execute = execute
    def fixed_execute(args, **kwargs):
        result = original_execute(args, **kwargs)
        if list(map(str,args))[:2] == ["git", "clone"]:
            runtime = Path(args[-1]).parent / "runtime"
            (runtime / "state/base.json").unlink(); (runtime/"state").rmdir(); runtime.rmdir()
        if "build-base" in list(map(str,args)):
            env = kwargs["env"]
            (Path(env["DEM_BETA_HOME"]) / "state/base.json").write_text('{"verified":true}')
        return result
    monkeypatch.setattr(auto, "run", fixed_execute)
    return d, calls, fixed_execute


def prepared(deployment):
    d, calls, execute = deployment
    auto.save(d.state / "deploy-approval.json", RECORD)
    d.prepare()
    return json.loads((d.state/"deploy-prepared.json").read_text())


def test_preparation_isolated_and_consumed(deployment):
    d, calls, _ = deployment
    record = prepared(deployment)
    assert not (d.state/"deploy-approval.json").exists()
    assert (d.repo/"deploy/beta/.env").read_text() == "original-env"
    assert not (d.state/"active-repo").exists()
    assert not (d.home/"flags/read_only").exists()
    assert not (d.home/"state/base.json").exists()
    docker = [(a,e) for a,e in calls if a[0] == "docker" and not (len(a)>1 and a[1] in {"ps", "network", "stop", "rm"})]
    assert all(e["DEM_BETA_HOME"] != str(d.home) for a,e in docker)
    assert all(e["COMPOSE_PROJECT_NAME"] == record["project"] for a,e in docker)
    assert not any("stop" in a or "api" in a for a,e in docker)
    assert any("validate" in a for a,e in docker)
    assert any("build-base" in a for a,e in docker)
    assert any("roles" in a for a,e in docker)


@pytest.mark.parametrize("failure", ["verify", "build", "validate", "db", "roles", "build-base", "status", "deadline"])
def test_preparation_failure_preserves_old_and_falls_back(deployment, monkeypatch, failure):
    d, calls, execute = deployment
    auto.save(d.state/"deploy-approval.json", RECORD)
    def fail(args, **kwargs):
        if failure in list(map(str,args)):
            raise auto.Rejected("injected")
        result = execute(args, **kwargs)
        if failure == "deadline" and "build-base" in args:
            d.now = lambda: NOW
        return result
    monkeypatch.setattr(auto, "run", fail)
    if failure == "verify":
        monkeypatch.setattr(auto, "verify", lambda *a: (_ for _ in ()).throw(auto.Rejected("mismatch")))
    d.prepare()
    assert not (d.state/"deploy-approval.json").exists()
    assert not (d.state/"deploy-prepared.json").exists()
    assert (d.repo/"deploy/beta/.env").read_text() == "original-env"
    assert not (d.state/"active-repo").exists()
    assert not (d.home/"flags/read_only").exists()
    assert json.loads((d.state/"deploy-event.json").read_text())["outcome"] == "preparation-failed"
    d.now = lambda: NOW
    assert d.scheduled() is False
    assert not any("stop" in a for a,e in calls)


def test_preparation_waits_for_hour_window(deployment):
    d, calls, _ = deployment
    d.now = lambda: NOW-timedelta(hours=2)
    auto.save(d.state/"deploy-approval.json", RECORD)
    d.prepare()
    assert not calls and (d.state/"deploy-approval.json").exists()


@pytest.mark.parametrize("offset", [-1, 0, 300, 301])
def test_scheduled_consumption_and_catchup(deployment, monkeypatch, offset):
    d, _, _ = deployment
    prepared(deployment)
    d.now = lambda: NOW+timedelta(seconds=offset)
    switched = []
    monkeypatch.setattr(d, "switch", lambda r: switched.append(r))
    if offset < 0:
        with pytest.raises(auto.Rejected):
            d.scheduled()
        assert (d.state/"deploy-prepared.json").exists()
    else:
        assert d.scheduled() is (offset <= 300)
        assert not (d.state/"deploy-prepared.json").exists()
        assert bool(switched) is (offset <= 300)
        assert d.scheduled() is False  # single use


def test_switch_one_reset_stop_before_prepare(deployment, monkeypatch):
    d, calls, _ = deployment
    record = prepared(deployment); calls.clear(); d.now = lambda: NOW
    monkeypatch.setattr(d, "critical", lambda *a: None)
    monkeypatch.setattr(d, "observations", lambda *a: None)
    d.switch(record)
    commands = [" ".join(a) for a,e in calls]
    stop = next(i for i,c in enumerate(commands) if "stop api web" in c)
    prepare = next(i for i,c in enumerate(commands) if "reset prepare" in c)
    swap = next(i for i,c in enumerate(commands) if "reset swap" in c)
    finish = next(i for i,c in enumerate(commands) if "reset finish" in c)
    assert stop < prepare < swap < finish
    assert sum("reset prepare" in c for c in commands) == 1
    assert not (d.home/"status/reset-error.json").exists()
    assert (d.state/"active-repo").read_text().strip() == record["repo"]


@pytest.mark.parametrize("failure", ["stop", "running", "prepare", "swap", "up", "critical", "finish"])
def test_switch_failure_freezes_no_rollback_or_retry(deployment, monkeypatch, failure):
    d, calls, execute = deployment
    record = prepared(deployment); calls.clear(); d.now = lambda: NOW
    def fail(args, **kwargs):
        values = list(map(str,args))
        if failure in values:
            raise auto.Rejected("injected")
        if failure == "running" and values[:2] == ["docker", "inspect"]:
            return "true"
        return execute(args, **kwargs)
    monkeypatch.setattr(auto, "run", fail)
    def critical(*args):
        if failure == "critical":
            raise auto.Rejected("wrong version")
    monkeypatch.setattr(d, "critical", critical)
    monkeypatch.setattr(d, "observations", lambda *a: None)
    with pytest.raises(auto.Rejected):
        d.switch(record)
    assert (d.home/"flags/read_only").exists()
    assert (d.home/"status/reset-error.json").exists()
    with pytest.raises(auto.Rejected, match="recovery"):
        d.scheduled()
    assert not any("start" in a for a,e in calls)


def test_noncritical_check_warns_and_finishes(deployment, monkeypatch):
    d, calls, _ = deployment
    record = prepared(deployment); d.now = lambda: NOW
    monkeypatch.setattr(d, "critical", lambda *a: None)
    monkeypatch.setattr(d, "observations", lambda *a: (_ for _ in ()).throw(auto.Rejected("header")))
    d.switch(record)
    assert json.loads((d.state/"deploy-event.json").read_text())["outcome"] == "deployed-check-warning"
    assert any("finish" in a for a,e in calls)


@pytest.mark.parametrize("bad", ["none", "image-ref", "image-id", "env", "health", "http", "body"])
def test_running_version_and_health_guard(deployment, monkeypatch, bad):
    d, _, _ = deployment
    def inspect(args, **kwargs):
        text = " ".join(map(str,args))
        if "image inspect" in text:
            return "sha256:expected"
        if "docker inspect" in text:
            service = "web" if str(args[-1]) == "web-id" else "api"
            return json.dumps([dict(Config=dict(Image=f"dem-beta-{service}:"+("d"*40 if bad == "image-ref" else RECORD["commit"]),
                Env=[] if bad == "env" else [f"DEM_BETA_COMMIT={RECORD['commit']}"]),
                Image="sha256:wrong" if bad == "image-id" else "sha256:expected",
                State=dict(Health=dict(Status="unhealthy" if bad == "health" else "healthy")))])
        if args[0] == "curl":
            if bad == "http":
                raise auto.Rejected("503")
            return '{"status":"wrong"}' if bad == "body" else '{"status":"ok"}'
        return ""
    monkeypatch.setattr(auto, "run", inspect)
    monkeypatch.setattr(d, "dc", lambda r,e,*a: a[-1]+"-id")
    if bad == "none":
        d.critical(d.repo, d.env, RECORD)
    else:
        with pytest.raises(auto.Rejected):
            d.critical(d.repo, d.env, RECORD)


def test_trusted_wrapper_and_locks_are_preserved():
    source = (ROOT/"deploy/beta/auto_deploy.py").read_text()
    shell = (ROOT/"deploy/beta/bin/dem-beta").read_text()
    assert source.index('if args.command == "scheduled-reset":') < source.index('with lock(deployment.state / "deploy.lock")')
    assert 'with lock(deployment.state / "operation.lock")' in source
    assert shell.index('exec python3 "$REPO/deploy/beta/auto_deploy.py"') < shell.index('flock -n 9')
    assert "scheduled-reset" in (ROOT/"deploy/beta/systemd/dem-beta-reset.service").read_text()
    assert "TimeoutStartSec=45min" in (ROOT/"deploy/beta/systemd/dem-beta-deploy-prepare.service").read_text()

@pytest.mark.parametrize("command", ["deploy-approve", "deploy-dry-run"])
def test_registration_and_dry_run(deployment, monkeypatch, command, capsys):
    d, _, _ = deployment
    monkeypatch.setattr(auto, "Deployment", lambda repo: d)
    monkeypatch.setattr(auto.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(auto, "approval", lambda *a: RECORD)
    monkeypatch.setattr(auto.os.sys, "argv", ["auto", str(d.repo), command, *RECORD.values()])
    before = sorted(d.state.iterdir())
    assert auto.main() == 0
    assert RECORD["commit"] in capsys.readouterr().out
    if command == "deploy-approve":
        assert json.loads((d.state/"deploy-approval.json").read_text()) == RECORD
    else:
        assert sorted(d.state.iterdir()) == before


def test_cancel_consumes_prepared_and_pending(deployment, monkeypatch):
    d, _, _ = deployment
    prepared(deployment)
    auto.save(d.state/"deploy-approval.json", RECORD)
    monkeypatch.setattr(auto, "Deployment", lambda repo: d)
    monkeypatch.setattr(auto.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(auto.os.sys, "argv", ["auto", str(d.repo), "deploy-cancel"])
    assert auto.main() == 0
    assert not (d.state/"deploy-approval.json").exists()
    assert not (d.state/"deploy-prepared.json").exists()
    d.now = lambda: NOW
    assert d.scheduled() is False


def test_read_refuses_non_root_writable_symlink_and_large(tmp_path, monkeypatch):
    # Unix metadata is explicit so Windows exercises the same permission guard.
    # Fresh module retains the real read function (fixture substitutes it elsewhere).
    path = tmp_path/"record"; path.write_text('{}')
    for mode, uid, size in [(0o100600, 0, 2), (0o100644, 0, 2), (0o100600, 10001, 2),
                             (0o120600, 0, 2), (0o100600, 0, 20000)]:
        monkeypatch.setattr(Path, "lstat", lambda p, m=mode,u=uid,s=size: SimpleNamespace(st_mode=m, st_uid=u, st_size=s))
        if mode == 0o100600 and uid == 0 and size == 2:
            assert auto.read(path) == {}
        else:
            with pytest.raises(auto.Rejected):
                auto.read(path)


@pytest.mark.parametrize("bad", ["none", "h2", "h1", "alt-svc", "header", "next-reset", "get"])
def test_public_observations_matrix(deployment, monkeypatch, bad):
    d, calls, _ = deployment
    (d.home/"status/status.json").write_text(json.dumps(dict(next_reset_at=RECORD["at"])))
    def curl(args, **kwargs):
        if args[-1].endswith('/api/config'):
            return json.dumps(dict(beta=dict(next_reset_at="wrong" if bad == "next-reset" else RECORD["at"])))
        if "-D" in args:
            version = '2' if '--http2' in args else '1.1'
            if (bad == 'h2' and version == '2') or (bad == 'h1' and version == '1.1'):
                version = '1.0'
            headers = ('Strict-Transport-Security: max-age=31536000\nX-Content-Type-Options: nosniff\n'
                       'Referrer-Policy: strict-origin-when-cross-origin\nPermissions-Policy: camera=(), microphone=(), geolocation=()\n'
                       "Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'\nCache-Control: no-cache, no-store\n"
                       'X-Robots-Tag: noindex\n')
            if bad == 'header':
                headers = headers.replace('nosniff','wrong')
            if bad == 'alt-svc':
                headers += 'Alt-Svc: h3=":443"\n'
            return headers+'\n'+version
        if bad == 'get':
            raise auto.Rejected('GET failed')
        return 'page'
    monkeypatch.setattr(auto, 'run', curl)
    if bad == 'none':
        d.observations(d.env)
    else:
        with pytest.raises(auto.Rejected):
            d.observations(d.env)


def test_preparation_releases_operation_lock_during_expensive_work(deployment, monkeypatch):
    d, calls, execute = deployment
    held = []
    from contextlib import contextmanager
    @contextmanager
    def checked_lock(path, **kwargs):
        held.append(path.name)
        try:
            yield
        finally:
            held.pop()
    monkeypatch.setattr(auto, 'lock', checked_lock)
    def checked_run(args, **kwargs):
        if args[0] == 'docker':
            assert 'operation.lock' not in held
        return execute(args, **kwargs)
    monkeypatch.setattr(auto, 'run', checked_run)
    prepared(deployment)
    assert not held


def test_early_direct_switch_does_not_stop_old_api(deployment):
    d, calls, _ = deployment
    record = prepared(deployment); calls.clear()
    d.now = lambda: NOW-timedelta(seconds=1)
    with pytest.raises(auto.Rejected):
        d.switch(record)
    assert not any('stop' in a for a,e in calls)


def test_freeze_blocks_deployment_and_baseline_rejection_falls_back(deployment, monkeypatch):
    d, calls, _ = deployment
    record = prepared(deployment); d.now = lambda: NOW
    (d.home/'flags/read_only').touch()
    assert d.scheduled() is False
    assert not any('stop' in a for a,e in calls)


def test_notification_records_deployment_result(deployment):
    d, _, _ = deployment
    spec = importlib.util.spec_from_file_location('notify_deploy', ROOT/'deploy/beta/notify.py')
    notify = importlib.util.module_from_spec(spec); spec.loader.exec_module(notify)
    d.event('deployed-check-warning')
    result = notify.operations(d.home, 0)
    assert 'deployed-check-warning' in result['deployment']
    assert 'PASSWORD' not in result['deployment']


def test_cancel_during_preparation_cannot_publish(deployment, monkeypatch):
    d, _, execute = deployment
    def cancel(args, **kwargs):
        result = execute(args, **kwargs)
        if 'build-base' in list(map(str,args)):
            auto.atomic(d.state/'deploy-cancelled', 'cancelled\n')
        return result
    monkeypatch.setattr(auto, 'run', cancel)
    auto.save(d.state/'deploy-approval.json', RECORD)
    d.prepare()
    assert not (d.state/'deploy-prepared.json').exists()
    assert json.loads((d.state/'deploy-event.json').read_text())['outcome'] == 'cancelled'


def test_fallback_child_starts_after_operation_lock_released(deployment, monkeypatch):
    d, _, execute = deployment
    from contextlib import contextmanager
    held = []
    @contextmanager
    def tracking(path, **kwargs):
        held.append(path.name)
        try:
            yield
        finally:
            held.pop()
    def child(args, **kwargs):
        if args[0] == '/usr/local/sbin/dem-beta':
            assert not held
            assert args[-1] == 'reset'
        return execute(args, **kwargs)
    monkeypatch.setattr(auto, 'lock', tracking)
    monkeypatch.setattr(auto, 'run', child)
    monkeypatch.setattr(auto, 'Deployment', lambda r: d)
    monkeypatch.setattr(auto.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(auto.os.sys, 'argv', ['auto', str(d.repo), 'scheduled-reset'])
    assert auto.main() == 0


def test_host_only_bootstrap_commit_can_differ_from_live_image(deployment, monkeypatch):
    d, _, _ = deployment
    d.baseline = 'd'*40
    monkeypatch.setattr(auto, 'run', lambda args, **kwargs: d.baseline if 'rev-parse' in args else '')
    auto.Deployment.check_baseline(d)
    assert d.env['DEM_BETA_COMMIT'] != d.baseline


def test_real_git_tag_peeling_and_retag_rejection(tmp_path, monkeypatch):
    import subprocess
    remote = tmp_path/'remote'; remote.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(remote),*args], stderr=subprocess.DEVNULL).decode().strip()
    git('init')
    (remote/'deploy/beta').mkdir(parents=True)
    (remote/'deploy/beta/host.py').write_text('host v1\n')
    git('add','.')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','base')
    base = git('rev-parse','HEAD')
    (remote/'app.py').write_text('raise RuntimeError("must never run during verification")\n')
    git('add','.')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','candidate')
    commit, tree = git('rev-parse','HEAD'), git('rev-parse','HEAD^{tree}')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','tag','-am','approved', RECORD['tag'])
    record = dict(RECORD,commit=commit,tree=tree)
    original = auto.run
    def local(args, **kwargs):
        args = list(args)
        if 'get-url' in args:
            return 'https://github.com/example/demo.git'
        args = [str(remote) if a == 'https://github.com/example/demo.git' else a for a in args]
        return original(args, **kwargs)
    monkeypatch.setattr(auto,'run',local)
    assert auto.verify(remote,tmp_path/'first',record,base) == commit
    git('tag','-f',RECORD['tag'],base)
    with pytest.raises(auto.Rejected,match='mismatch'):
        auto.verify(remote,tmp_path/'second',record,base)


def test_actual_version_mismatch_freezes_before_finish(deployment, monkeypatch):
    d, calls, execute = deployment
    record = prepared(deployment); calls.clear(); d.now = lambda: NOW
    def wrong_image(args, **kwargs):
        if list(map(str,args))[:2] == ['docker','inspect'] and '--format' not in args:
            return json.dumps([dict(Config=dict(Image='dem-beta-api:wrong'),Image='sha256:wrong')])
        return execute(args, **kwargs)
    monkeypatch.setattr(auto,'run',wrong_image)
    with pytest.raises(auto.Rejected,match='version mismatch'):
        d.switch(record)
    assert (d.home/'flags/read_only').exists()
    assert (d.home/'status/reset-error.json').exists()
    assert not any('finish' in a for a,e in calls)



def test_scheduled_lock_contention_returns_75(deployment, monkeypatch):
    d, _, _ = deployment
    def busy(*args, **kwargs):
        raise auto.Busy("busy")
    monkeypatch.setattr(auto, 'lock', busy)
    monkeypatch.setattr(auto, 'Deployment', lambda repo: d)
    monkeypatch.setattr(auto.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(auto.os.sys, 'argv', ['auto', str(d.repo), 'scheduled-reset'])
    assert auto.main() == 75

# Fix 1: Compose resource model, interruption notifications and cleanup matrix.
def notification_module():
    spec = importlib.util.spec_from_file_location('auto_notify', ROOT/'deploy/beta/notify.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_preparation_compose_has_no_live_proxy_or_certificates():
    import yaml
    prep = yaml.safe_load((ROOT/'deploy/beta/prepare.compose.yml').read_text())
    live = yaml.safe_load((ROOT/'deploy/beta/compose.yml').read_text())
    assert set(prep['services']) == {'db','tools'}
    assert prep['networks'] == {'database': {'internal': True}}
    assert set(prep['volumes']) == {'pgdata'}
    assert prep['volumes']['pgdata'] == {'external': True, 'name': '${DEM_BETA_DB_VOLUME:?set candidate volume}'}
    assert '172.30.42' not in json.dumps(prep)
    assert 'ipv4_address' not in json.dumps(prep)
    for name, service in prep['services'].items():
        assert not service.get('ports')
        assert set(service['networks']) == {'database'}
        expected = dict(live['services'][name])
        if name == 'db':
            expected['restart'] = 'no'
        assert service == expected  # DB guards, roles, mounts and limits unchanged.


def test_stable_live_resources_keep_existing_host_names():
    import yaml
    live = yaml.safe_load((ROOT/'deploy/beta/compose.yml').read_text())
    assert live['name'] == 'dem-beta'
    assert live['volumes']['caddy_data']['name'] == 'dem-beta_caddy_data'
    assert live['volumes']['caddy_config']['name'] == 'dem-beta_caddy_config'
    assert live['volumes']['pgdata'] == {'external': True, 'name': '${DEM_BETA_DB_VOLUME:-dem-beta_pgdata}'}
    assert live['networks']['proxy']['internal'] is True
    assert live['networks']['proxy']['ipam']['config'] == [{'subnet': '172.30.42.0/24'}]
    assert live['services']['web']['networks']['proxy']['ipv4_address'] == '172.30.42.2'
    assert live['services']['api']['networks']['proxy']['ipv4_address'] == '172.30.42.3'
    assert '--forwarded-allow-ips' in (ROOT/'deploy/beta/api.Dockerfile').read_text()
    assert '172.30.42.2' in (ROOT/'deploy/beta/api.Dockerfile').read_text()
    assert 'docker volume create "${DEM_BETA_DB_VOLUME:-dem-beta_pgdata}"' in (ROOT/'deploy/beta/install.sh').read_text()


def test_caddy_validate_has_no_live_resources(deployment):
    d, calls, _ = deployment
    prepared(deployment)
    validate = next(a for a,e in calls if 'validate' in a)
    assert validate[:2] == ['docker','run']
    assert validate[validate.index('--network')+1] == 'none'
    assert '--volume' not in validate and '-v' not in validate and '--mount' not in validate
    assert '--rm' in validate
    assert any(a[0:2] == ['docker','compose'] and 'prepare.compose.yml' in ' '.join(a) for a,e in calls)
    assert not any(a[:2] == ['docker','compose'] and str(ROOT/'deploy/beta/compose.yml') in a for a,e in calls)


def test_no_failure_is_delivered_at_any_successful_switch_step(deployment, monkeypatch):
    d, calls, execute = deployment
    record = prepared(deployment); d.now = lambda: NOW
    notify = notification_module()
    (d.home/'contacts').mkdir()
    sent = []
    monkeypatch.setattr(notify,'post',lambda webhook, body: sent.append(body['text']) or True)
    monkeypatch.setattr(notify,'traffic_notifications',lambda *a: True)
    checked = []
    def during(args, **kwargs):
        assert notify.deliver(d.home, 'unused-local-fake', NOW)
        checked.append(d.stage)
        return execute(args, **kwargs)
    monkeypatch.setattr(auto,'run',during)
    monkeypatch.setattr(d,'critical',lambda *a: None)
    monkeypatch.setattr(d,'observations',lambda *a: None)
    d.switch(record)
    assert len(checked) > 10
    assert {'stop','prepare','swap','start','finish'} <= set(checked)
    assert not any('Beta reset failed' in text or 'switch-failed' in text or 'deployment failed' in text for text in sent)
    assert not (d.state/'deploy-switching.json').exists()
    assert not (d.home/'status/reset-error.json').exists()


@pytest.mark.parametrize('seconds,failed', [(0,False),(1199,False),(1200,True),(2000,True)])
def test_interrupted_switch_notification_deadline(deployment, seconds, failed):
    d, _, _ = deployment
    d.switch_time = NOW.isoformat(); d.stage = 'swap'; d.switching(); d.freeze()
    notify = notification_module()
    events = notify.operations(d.home,0,now=NOW+timedelta(seconds=seconds))
    assert ('deployment_interrupted' in events) is failed
    assert 'reset' not in events
    with pytest.raises(auto.RecoveryRequired):
        d.scheduled()
    assert (d.home/'flags/read_only').exists()


@pytest.mark.parametrize('origin',['ordinary-reset','deployment-interrupted'])
def test_recovery_block_notifies_each_scheduled_occurrence(deployment, origin):
    d, _, _ = deployment
    if origin == 'ordinary-reset':
        auto.save(d.home/'status/reset-error.json',dict(failed_at=NOW.isoformat(),stage='prepare'))
    else:
        d.switch_time=NOW.isoformat();d.stage='start';d.switching()
    records=[]
    for day in (7,14):
        d.now=lambda day=day: NOW+timedelta(days=day)
        with pytest.raises(auto.RecoveryRequired):
            d.scheduled()
        records.append((d.state/'deploy-event.json').read_text())
    assert records[0] != records[1]
    assert all(json.loads(value)['outcome']=='recovery-blocked' for value in records)


@pytest.mark.parametrize('name',['deploy-approval.json','deploy-consumed.json','deploy-prepared.json'])
@pytest.mark.parametrize('bad',['json','timestamp','unsafe','unlink-race'])
def test_bad_records_or_unlink_race_run_the_normal_reset(deployment, monkeypatch, name, bad):
    d, calls, execute = deployment; d.now=lambda: NOW
    path=d.state/name
    path.write_text('broken-json' if bad=='json' else json.dumps(dict(RECORD,at='not-a-date' if bad=='timestamp' else RECORD['at'])))
    if bad=='unsafe':
        original=auto.read
        def unsafe(p):
            if p == path:
                raise auto.Rejected('unsafe deployment record')
            return original(p)
        monkeypatch.setattr(auto,'read',unsafe)
    if bad=='unlink-race':
        original=Path.unlink; raced=[]
        def race(p,*a,**k):
            if p==path and not raced:
                raced.append(True);original(p,missing_ok=True);raise FileNotFoundError('concurrent consumption')
            return original(p,*a,**k)
        monkeypatch.setattr(Path,'unlink',race)
    monkeypatch.setattr(auto,'Deployment',lambda repo: d)
    monkeypatch.setattr(auto.os,'geteuid',lambda:0,raising=False)
    monkeypatch.setattr(auto.os.sys,'argv',['auto',str(d.repo),'scheduled-reset'])
    assert auto.main() == 0
    assert any(a == ['/usr/local/sbin/dem-beta','reset'] for a,e in calls)
    assert not path.exists()
    if bad!='unlink-race' or name=='deploy-prepared.json':
        assert (d.state/'deploy-event.json').exists()


def test_unexpected_pre_switch_exception_still_calls_normal_reset(deployment, monkeypatch):
    d,calls,_=deployment
    monkeypatch.setattr(d,'scheduled',lambda: (_ for _ in ()).throw(OSError('injected before switch')))
    monkeypatch.setattr(auto,'Deployment',lambda repo:d)
    monkeypatch.setattr(auto.os,'geteuid',lambda:0,raising=False)
    monkeypatch.setattr(auto.os.sys,'argv',['auto',str(d.repo),'scheduled-reset'])
    assert auto.main()==0
    assert any(a==['/usr/local/sbin/dem-beta','reset'] for a,e in calls)
    assert json.loads((d.state/'deploy-event.json').read_text())['outcome']=='pre-switch-rejected'


def test_early_invocation_keeps_approval_and_notifies(deployment):
    d,calls,_=deployment
    auto.save(d.state/'deploy-approval.json',RECORD)
    with pytest.raises(auto.Early):
        d.scheduled()
    assert (d.state/'deploy-approval.json').exists()
    assert json.loads((d.state/'deploy-event.json').read_text())['outcome']=='early-reset-rejected'
    assert not any(a==['/usr/local/sbin/dem-beta','reset'] for a,e in calls)


@pytest.mark.parametrize('bad', ["'", '"', '$', '#', '\\', '\n', '`', '\x00'])
def test_env_literal_subset_rejects_ambiguous_characters(deployment,bad):
    d,_,_=deployment
    with pytest.raises(auto.Rejected):
        d.env_file(d.repo,dict(DEM_BETA_TEST='prefix'+bad+'suffix'))
    assert (d.repo/'deploy/beta/.env').read_text()=='original-env'


@pytest.mark.parametrize('value',['','abc-12_./:@%+=, ?&','Mon 04:00 Asia/Tokyo'])
def test_env_literal_subset_roundtrips_through_bash(deployment,value):
    import shutil,subprocess
    d,_,_=deployment
    d.env_file(d.repo,dict(DEM_BETA_TEST=value))
    text=(d.repo/'deploy/beta/.env').read_text()
    assert text == "DEM_BETA_TEST='"+value+"'\n"
    bash='C:/Program Files/Git/bin/bash.exe' if os.name=='nt' else shutil.which('bash')
    result=subprocess.check_output([bash,'-c','source "$1"; printf %s "$DEM_BETA_TEST"','_', (d.repo/'deploy/beta/.env').as_posix()])
    assert result.decode()==value


@pytest.mark.parametrize('cause',['failure','cancel','expired','killed-prepare','killed-reset','success'])
def test_candidate_containers_are_reaped_without_touching_live(deployment,monkeypatch,cause):
    d,calls,execute=deployment
    containers={};stopped=[];networks={}
    class Killed(BaseException):
        pass
    def docker(args,**kwargs):
        a=list(map(str,args))
        if a[:2]==['docker','ps']:
            project=next(x.split('=',2)[-1] for x in a if x.startswith('label='))
            return containers.get(project,'')
        if a[:3]==['docker','network','ls']:
            return ''
        if a[:2]==['docker','stop']:
            stopped.extend(a[4:])
            for project,identity in list(containers.items()):
                if identity in stopped: containers[project]=''
        if a[:2]==['docker','compose'] and 'prepare.compose.yml' in ' '.join(a) and 'up' in a:
            project=a[a.index('--project-name')+1]; containers[project]='b'*12
        if 'roles' in a:
            if cause=='failure': raise auto.Rejected('failed base setup')
            if cause in {'killed-prepare','killed-reset'}: raise Killed()
        result=execute(args,**kwargs)
        if 'build-base' in a and cause=='cancel':auto.atomic(d.state/'deploy-cancelled','cancelled\n')
        return result
    monkeypatch.setattr(auto,'run',docker)
    containers['dem-beta']='a'*12
    auto.save(d.state/'deploy-approval.json',RECORD)
    if cause.startswith('killed-'):
        with pytest.raises(Killed):d.prepare()
        assert 'b'*12 not in stopped
        if cause=='killed-prepare':d.prepare()
        else:d.now=lambda:NOW;assert d.scheduled() is False
    else:
        d.prepare()
        if cause=='expired':
            # An orphan from an interrupted final cleanup is reaped at reset too.
            project=next(p for p in containers if p!='dem-beta');containers[project]='c'*12
            d.now=lambda:NOW+timedelta(seconds=301);assert d.scheduled() is False
            assert 'c'*12 in stopped
    assert 'b'*12 in stopped
    assert 'a'*12 not in stopped
    assert containers['dem-beta']=='a'*12
    assert not any(a[:3]==['docker','volume','rm'] for a,e in calls)


def test_successful_switch_stops_old_db_and_forces_generation_volume(deployment,monkeypatch):
    d,calls,_=deployment; record=prepared(deployment);calls.clear();d.now=lambda:NOW
    monkeypatch.setattr(d,'critical',lambda *a:None);monkeypatch.setattr(d,'observations',lambda *a:None)
    d.switch(record)
    compose=[(a,e) for a,e in calls if a[:2]==['docker','compose']]
    assert all(a[a.index('--project-name')+1]=='dem-beta' for a,e in compose)
    assert any(a[-4:]==['stop','api','web','db'] for a,e in compose)
    db_start=next((a,e) for a,e in compose if 'up' in a and a[-1]=='db')
    assert '--force-recreate' in db_start[0]
    assert db_start[1]['DEM_BETA_DB_VOLUME']==record['volume']
    assert not any('down' in a for a,e in compose)


def test_two_successive_generations_keep_stable_project(deployment,monkeypatch):
    d,calls,_=deployment
    monkeypatch.setattr(d,'critical',lambda *a:None);monkeypatch.setattr(d,'observations',lambda *a:None)
    volumes=[]
    for week in (0,1):
        at=NOW+timedelta(days=7*week);d.now=lambda at=at:at-timedelta(minutes=30)
        auto.save(d.state/'deploy-approval.json',dict(RECORD,at=at.isoformat()))
        d.prepare();record=auto.read(d.state/'deploy-prepared.json');volumes.append(record['volume'])
        d.now=lambda at=at:at;assert d.scheduled() is True
        d.repo=Path(record['repo']);d.env.update(DEM_BETA_COMMIT=record['commit'],DEM_BETA_DB_VOLUME=record['volume'],COMPOSE_PROJECT_NAME='dem-beta')
    assert volumes[0]!=volumes[1]
    live=[a for a,e in calls if a[:2]==['docker','compose'] and 'prepare.compose.yml' not in ' '.join(a)]
    assert all(a[a.index('--project-name')+1]=='dem-beta' for a in live)


def test_cleanup_refuses_forged_live_project_registry(deployment):
    d,calls,_=deployment;record=prepared(deployment);calls.clear()
    registry=d.state/'deploy-candidates'/(record['id']+'.json')
    auto.save(registry,dict(record,project='dem-beta'))
    d.cleanup_candidates()
    assert not calls
    assert json.loads((d.state/'deploy-event.json').read_text())['outcome']=='cleanup-failed'


@pytest.mark.parametrize('failure,stage',[('stop','stop'),('prepare','prepare'),('swap','swap'),('up','start'),('critical','ready'),('finish','finish')])
def test_failure_record_reports_actual_stage(deployment,monkeypatch,failure,stage):
    d,_,execute=deployment;record=prepared(deployment);d.now=lambda:NOW
    def fail(args,**kwargs):
        if failure in list(map(str,args)):raise auto.Rejected('injected stage')
        return execute(args,**kwargs)
    monkeypatch.setattr(auto,'run',fail)
    def critical(*a):
        if failure=='critical':raise auto.Rejected('critical')
    monkeypatch.setattr(d,'critical',critical);monkeypatch.setattr(d,'observations',lambda *a:None)
    with pytest.raises(auto.Rejected):d.switch(record)
    assert auto.read(d.home/'status/reset-error.json')['stage']==stage
    assert not (d.state/'deploy-switching.json').exists()


def test_pre_switch_notification_failure_does_not_skip_reset(deployment,monkeypatch):
    d,calls,_=deployment
    (d.state/'deploy-approval.json').write_text('corrupt')
    monkeypatch.setattr(d,'event',lambda *a: (_ for _ in ()).throw(OSError('cannot record')))
    monkeypatch.setattr(auto,'Deployment',lambda repo:d)
    monkeypatch.setattr(auto.os,'geteuid',lambda:0,raising=False)
    monkeypatch.setattr(auto.os.sys,'argv',['auto',str(d.repo),'scheduled-reset'])
    assert auto.main()==0
    assert any(a==['/usr/local/sbin/dem-beta','reset'] for a,e in calls)



def test_early_reset_notification_failure_never_runs_reset(deployment,monkeypatch):
    d,calls,_=deployment;auto.save(d.state/'deploy-approval.json',RECORD)
    monkeypatch.setattr(d,'event',lambda *a: (_ for _ in ()).throw(OSError('cannot record')))
    monkeypatch.setattr(auto,'Deployment',lambda repo:d)
    monkeypatch.setattr(auto.os,'geteuid',lambda:0,raising=False)
    monkeypatch.setattr(auto.os.sys,'argv',['auto',str(d.repo),'scheduled-reset'])
    assert auto.main()==1
    assert (d.state/'deploy-approval.json').exists()
    assert not any(a==['/usr/local/sbin/dem-beta','reset'] for a,e in calls)
