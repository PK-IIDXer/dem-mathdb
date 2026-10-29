"""Count-only traffic analysis, incident delivery and privacy regression tests."""
import ast
from datetime import datetime, timedelta, timezone
import gzip
import importlib.util
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location('traffic_test_' + name, ROOT / 'deploy/beta' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

traffic, notify = load('traffic'), load('notify')
NOW = datetime(2026, 10, 30, 0, 5, tzinfo=timezone.utc)
STAMP = NOW.timestamp()
CANARIES = ['198.51.100.77', '/canary-path-7f3a', 'canary-ua-7f3a', 'canary-host.example', '?q=canary-7f3a']

@pytest.fixture
def home(tmp_path, monkeypatch):
    for name in ['logs', 'flags', 'host-state', 'contacts', 'status']:
        (tmp_path / name).mkdir()
    (tmp_path / 'logs/access.log').write_text('')
    monkeypatch.setattr(notify.shutil, 'disk_usage', lambda _: type('Usage', (), dict(used=10, total=100))())
    return tmp_path


def line(stamp=STAMP, status=200, uri='/api/stats', method='GET', ip='198.51.100.77', via=True):
    return json.dumps(dict(ts=stamp, status=status, request=dict(remote_ip=ip, method=method, uri=uri,
                      host='canary-host.example', headers={'User-Agent': ['canary-ua-7f3a']}),
                      resp_headers={'Via': ['1.1 Caddy'], 'Content-Type': ['application/json'], 'Content-Length': [str(min(traffic.MAINTENANCE_LENGTHS))]} if via else {})) + '\n'


def write(home, lines):
    (home / 'logs/access.log').write_text(''.join(lines), encoding='utf8')


def result(home):
    return traffic.analyze(home, STAMP)


def assert_private(value):
    text = json.dumps(value)
    assert not any(canary in text for canary in CANARIES)
    assert not re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)


def test_rotation_gzip_overlap_and_repeated_lines(home):
    duplicate, older = line(), line(STAMP - 200, 429)
    write(home, [duplicate, duplicate])
    rotated = home / 'logs/access-2026-10-30T00-04-00.000-size.log.gz'
    with gzip.open(rotated, 'wt') as stream:
        stream.write(duplicate + older)
    old = home / 'logs/access-2026-10-29T23-59-00.000.log.gz'
    with gzip.open(old, 'wt') as stream:
        stream.write(line(STAMP - 300))
    measured = result(home)
    assert measured['five']['total'] == 4  # Same-file multiplicity kept; overlap counted once.
    assert measured['five']['limited'] == 1
    assert traffic.analyze(home, STAMP, [rotated, rotated])['five']['total'] == 2
    assert_private(measured)


def test_invalid_large_future_rows_and_window_edges(home):
    bad = ['{\n', line(float('nan')), line(float('inf')), line(True), line(status=True),
           line(status=99), line(status=600), line(ip='::1'), line(ip=123), line(STAMP + 60),
           'x' * (traffic.MAX_LINE + 100) + '\n']
    write(home, bad + [line(STAMP - 300), line(STAMP - 300.001), line(STAMP - 3600),
                       line(STAMP - 3600.001), line(STAMP + 59), line()])
    measured = result(home)
    assert measured['invalid_rows'] == len(bad)
    assert measured['five']['total'] == 2
    assert measured['hour']['total'] == 4
    assert measured['scanned_rows'] == 17


@pytest.mark.parametrize('case', ['missing', 'directory', 'symlink', 'unreadable'])
def test_current_log_unreadable(home, monkeypatch, case):
    path = home / 'logs/access.log'
    if case == 'missing':
        path.unlink()
    elif case == 'directory':
        path.unlink(); path.mkdir()
    elif case == 'symlink':
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda p: p == path or original(p))
    else:
        original = traffic.os.open
        def denied(p, *args, **kwargs):
            if p == path:
                raise PermissionError('canary-path-7f3a')
            return original(p, *args, **kwargs)
        monkeypatch.setattr(traffic.os, 'open', denied)
    assert 'log_unreadable' in traffic.findings(result(home))


def test_invalid_percentage_boundary(home):
    write(home, ['{\n'] * 19 + [line()] * 1981)
    assert 'log_unreadable' not in traffic.findings(result(home))
    write(home, ['{\n'] * 20 + [line()] * 1980)
    assert 'log_unreadable' in traffic.findings(result(home))
    write(home, ['{\n'] * 20 + [line()] * 1981)
    assert 'log_unreadable' not in traffic.findings(result(home))


@pytest.mark.parametrize('kind,key,window,threshold', [
    ('api_errors', 'errors', 'five', 10), ('rate_limited', 'limited', 'five', 300),
    ('source_volume', 'largest_source', 'five', 3000), ('total_volume', 'total', 'five', 10000),
    ('writes', 'writes', 'hour', 500), ('writes', 'largest_writer', 'hour', 150),
])
def test_threshold_exact_and_one_below(home, kind, key, window, threshold):
    measured = result(home)
    measured[window][key] = threshold - 1
    assert kind not in traffic.findings(measured)
    measured[window][key] = threshold
    assert kind in traffic.findings(measured)


def test_freeze_503_and_upstream_successful_writes(home):
    write(home, [line(status=503, uri='/api/theorems', method='POST')] * 10 +
                [line(status=503)] * 2 + [line(uri='/api/theorems', method='POST')] * 3 +
                [line(uri='/api/theorems', method='POST', via=False)] * 4)
    assert result(home)['five']['errors'] == 12
    (home / 'flags/read_only').touch()
    measured = result(home)
    assert measured['five']['errors'] == 2
    assert measured['hour']['writes'] == 3
    assert measured['five']['origins'] == {'upstream': 15, 'edge_or_unknown': 4}


def test_all_routes_match_webapi_classification():
    from webapi.main import app
    from webapi import beta
    from starlette.routing import Match
    routes = []
    for included in app.router.routes:
        routes.extend(included.effective_route_contexts() if hasattr(included, 'effective_route_contexts') else [included])
    assert set(traffic.HEAVY) == beta.HEAVY_ROUTES
    assert traffic.PURE_POSTS == beta.PURE_POSTS
    for candidate in routes:
        if not hasattr(candidate, 'methods'):
            continue
        path = re.sub(r'\{[^}]+\}', '1', candidate.path)
        for method in ['GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE']:
            scope = dict(type='http', method=method, path=path, root_path='')
            matched = next((r.path for r in routes if r.matches(scope)[0] == Match.FULL), '<unmatched>')
            actual, heavy, export, forbidden = traffic.classify(method, '/api' + path)
            expected = 'contact' if method == 'POST' and matched == '/contact' else beta.category(method, matched)
            assert actual == expected, (path, method)
            assert heavy == (matched in beta.HEAVY_ROUTES), (path, method)
            assert export == (method == 'GET' and matched == '/workspace/export')
            expected_forbidden = matched in traffic.DOCS or (method, matched) in {('POST', '/symbol-roles'), ('GET', '/workspace/export')}
            assert forbidden == expected_forbidden, (path, method)
    # Detect changes to the beta-disabled predicates too, not just copied constants.
    tree = ast.parse(inspect.getsource(beta.BetaMiddleware))
    disabled = []
    docs = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        if 'beta.disabled' in body:
            disabled.append(ast.unparse(node.test))
        if 'JSONResponse' in body and '404' in body and isinstance(node.test, ast.Compare) and isinstance(node.test.comparators[0], ast.Set):
            docs = ast.literal_eval(node.test.comparators[0])
    assert docs == traffic.DOCS
    assert set(disabled) == {"scope['method'] == 'POST' and route == '/symbol-roles'", "scope['method'] == 'GET' and route == '/workspace/export'"}


def test_period_reminders_recovery_and_failed_start(home):
    state = traffic.empty_state()
    conditions = {'api_errors': {'count': 10}}
    traffic.advance(state, conditions, STAMP)
    record, phase, _ = traffic.pending(state, STAMP)[0]
    assert phase == 'started'
    assert traffic.pending(state, STAMP + 300)[0][1] == 'started'  # Retry until acknowledgement.
    record['last_sent'] = STAMP
    for seconds in range(300, 3600, 300):
        traffic.advance(state, conditions, STAMP + seconds)
        assert not traffic.pending(state, STAMP + seconds)
    assert traffic.pending(state, STAMP + 3600)[0][1] == 'continuing'
    record['last_sent'] = STAMP + 3600
    traffic.advance(state, {}, STAMP + 3900)
    traffic.advance(state, {}, STAMP + 5699)
    assert not traffic.pending(state, STAMP + 5699)
    traffic.advance(state, {}, STAMP + 5700)
    assert traffic.pending(state, STAMP + 5700)[0][1] == 'resolved'
    record['recovery_sent'] = STAMP + 5700
    assert not traffic.pending(state, STAMP + 6000)
    traffic.advance(state, conditions, STAMP + 7000)
    active = state['incidents']['api_errors'][-1]
    active['last_sent'] = STAMP + 7000
    traffic.advance(state, {}, STAMP + 10500)
    assert not traffic.pending(state, STAMP + 10600)  # Clearing is not continuing.


def test_daily_counts_probes_shares_and_partial_coverage(home):
    midnight = STAMP // 86400 * 86400
    write(home, [line(midnight - 86400 - 1), line(midnight - 1, uri='/.env?q=canary-7f3a'),
                line(midnight - 2, uri='/canary-path-7f3a?q=canary-7f3a'), line(midnight)])
    measured = traffic.analyze(home, STAMP, daily=True)
    text = traffic.daily_text(measured, traffic.empty_state())
    assert measured['day']['total'] == 2
    assert measured['day']['probing'] == measured['day']['probing_sources'] == 1
    assert measured['day']['top_percent'] == [100.0]
    assert not measured['partial']
    assert 'complete' in text
    assert_private(text)
    write(home, [line(midnight - 1)])
    assert 'partially missing' in traffic.daily_text(traffic.analyze(home, STAMP, daily=True), traffic.empty_state())


@pytest.mark.parametrize('pattern', traffic.PROBES)
def test_probe_patterns(home, pattern):
    write(home, [line(STAMP - 3600, uri='/' + pattern.lstrip('/'))])
    assert result(home)['hour']['probing'] == 1


def test_analysis_timeout_and_bounded_read(home):
    with pytest.raises(TimeoutError):
        traffic.analyze(home, STAMP, clock=lambda: 1, seconds=0)
    source = inspect.getsource(traffic.analyze)
    assert 'readline(MAX_LINE + 1)' in source and 'read()' not in source


def traffic_setup(home, monkeypatch, analysis=None):
    messages = []
    monkeypatch.setattr(notify, 'traffic_module', lambda: traffic)
    monkeypatch.setattr(notify, 'analyze_traffic', analysis or (lambda *_: result(home)))
    monkeypatch.setattr(traffic, 'run_analysis', lambda home, stamp, logs=None, daily=False: traffic.analyze(home, stamp, logs, daily=daily))
    def post(_url, value):
        messages.append(value)
        return True
    monkeypatch.setattr(notify, 'post', post)
    return messages


def test_delivery_retry_daily_once_and_no_two_days_old(home, monkeypatch):
    messages = traffic_setup(home, monkeypatch)
    attempts = []
    def post(_url, value):
        attempts.append(value)
        return len(attempts) != 1
    monkeypatch.setattr(notify, 'post', post)
    assert not notify.traffic_notifications(home, 'not-real', NOW)
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=5))
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=10))
    assert len(attempts) == 2
    state = json.loads((home / 'host-state/traffic-state.json').read_text())
    assert state['daily_sent'] == '2026-10-29'
    later = NOW + timedelta(days=2)
    monkeypatch.setattr(notify, 'analyze_traffic', lambda *_: traffic.analyze(home, later.timestamp()))
    assert notify.traffic_notifications(home, 'not-real', later)
    assert '2026-10-31T00:00:00Z' in attempts[-1]['text']
    assert len(attempts) == 3


@pytest.mark.parametrize('failure', ['exception', 'deadline', 'unreadable'])
def test_analysis_failure_never_blocks_contacts_and_is_deduplicated(home, monkeypatch, failure):
    def analysis(*_):
        if failure == 'exception':
            raise RuntimeError('/canary-path-7f3a 198.51.100.77')
        if failure == 'deadline':
            return {'failure': True}
        (home / 'logs/access.log').unlink(missing_ok=True)
        return result(home)
    messages = traffic_setup(home, monkeypatch, analysis)
    contact = home / 'contacts' / ('contact-20261030T000500000000Z-' + '0' * 31 + '1.json')
    contact.write_text(json.dumps(dict(kind='bug', received_at=NOW.isoformat(), target_url=None, message='help', reply_to=None)))
    assert notify.deliver(home, 'not-real', NOW)
    assert messages[0]['text'].startswith('Beta contact:')
    kind = 'log_unreadable' if failure == 'unreadable' else 'analysis_failed'
    assert sum(kind + ' started' in value['text'] for value in messages) == 1
    assert notify.deliver(home, 'not-real', NOW + timedelta(minutes=5))
    assert sum(kind + ' started' in value['text'] for value in messages) == 1
    assert_private(messages)


def test_hard_process_timeout_uses_existing_transport_only(home, monkeypatch):
    captured = {}
    def run(command, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(command, 30)
    monkeypatch.setattr(notify.subprocess, 'run', run)
    assert notify.analyze_traffic(home, NOW) == {'failure': True}
    assert captured['timeout'] == 20
    assert captured['stderr'] == subprocess.DEVNULL


def test_all_payloads_state_and_dry_run_are_private(home, monkeypatch):
    write(home, [line(uri='/canary-path-7f3a?q=canary-7f3a', status=429)] * 300 +
                [line(uri='/api/theorems?q=canary-7f3a', method='POST')] * 150)
    messages = traffic_setup(home, monkeypatch)
    assert notify.traffic_notifications(home, 'not-real', NOW)
    assert_private(messages)
    assert all(len(value['text'].encode()) <= 2700 for value in messages)
    assert all(value['blocks'][0]['text']['type'] == 'plain_text' and value['parse'] == 'none' for value in messages)
    assert_private(json.loads((home / 'host-state/traffic-state.json').read_text()))
    assert_private(traffic.dry_run(home, STAMP, None))


def test_cli_is_root_terminal_only_and_never_prints_ip(home, monkeypatch, capsys):
    write(home, [line(uri='/canary-path-7f3a?q=canary-7f3a')])
    monkeypatch.setattr(traffic.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(traffic.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr(sys, 'argv', ['traffic', 'dry-run', '--home', str(home), '--log', str(home / 'logs/access.log'), '--now', NOW.isoformat()])
    assert traffic.main() == 0
    assert_private(capsys.readouterr().out)
    monkeypatch.setattr(traffic.sys.stdout, 'isatty', lambda: False)
    assert traffic.main() == 1


def test_host_code_is_python312_stdlib_and_no_other_sender():
    for path in ['traffic.py', 'notify.py']:
        source = (ROOT / 'deploy/beta' / path).read_text(encoding='utf8')
        tree = ast.parse(source, feature_version=(3, 12))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(name.name.split('.')[0] in sys.stdlib_module_names for name in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module.split('.')[0] in sys.stdlib_module_names
    assert not any(isinstance(node, ast.Attribute) and node.attr in {'urlopen', 'request', 'post'} for node in ast.walk(ast.parse(inspect.getsource(traffic))))
    wrapper = (ROOT / 'deploy/beta/bin/dem-beta').read_text()
    assert wrapper.index('"$command" == traffic') < wrapper.index('operation.lock')
    assert 'TimeoutStartSec=2min' in (ROOT / 'deploy/beta/systemd/dem-beta-notify.service').read_text()



def test_real_analysis_worker(home):
    write(home, [line()])
    measured = notify.analyze_traffic(home, NOW)
    assert measured['five']['total'] == 1
    assert_private(measured)
    daily = traffic.run_analysis(home, STAMP, daily=True)
    assert 'day' in daily and 'five' not in daily
    assert_private(daily)


def test_alert_failure_retry_and_recovery_delivery(home, monkeypatch):
    write(home, [line(status=500)] * 10)
    messages = traffic_setup(home, monkeypatch)
    failed = set()
    def post(_url, value):
        messages.append(value)
        text = value['text']
        phase = 'started' if 'api_errors started' in text else 'resolved' if 'api_errors resolved' in text else None
        if phase and phase not in failed:
            failed.add(phase)
            return False
        return True
    monkeypatch.setattr(notify, 'post', post)
    assert not notify.traffic_notifications(home, 'not-real', NOW)
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=5))
    count = len(messages)
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=10))
    assert len(messages) == count
    write(home, [])
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=15))
    assert not notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=45))
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=50))
    count = len(messages)
    assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=55))
    assert len(messages) == count
    assert_private(messages)



def test_frozen_full_pool_and_uvicorn_503_still_count(home):
    from webapi import beta
    from webapi import deps
    from webapi.main import app
    from fastapi.responses import JSONResponse
    (home / 'flags/read_only').touch()
    assert traffic.MAINTENANCE_DETAILS[0] in inspect.getsource(beta.BetaMiddleware)
    assert 'Beta write state: {state}' in inspect.getsource(deps.dem_services)
    responses = [beta.reject_response(beta.BetaReject(503, 'beta.maintenance', detail), '/', 'write') for detail in traffic.MAINTENANCE_DETAILS]
    errors = [beta.reject_response(beta.BetaReject(503, 'beta.full', 'Beta write state: full'), '/', 'write'),
              beta.reject_response(beta.BetaReject(503, 'beta.database_busy', 'Database connections are busy', 2), '/', 'write'),
              JSONResponse(status_code=503, content={'detail': 'unknown error'}),
              type('Plain503', (), {'headers': {'content-type': 'text/plain', 'content-length': '19'}})()]
    rows = []
    for response in responses + errors:
        row = json.loads(line(status=503, uri='/api/theorems', method='POST'))
        row['resp_headers'] = {**{key: [value] for key, value in response.headers.items()}, 'Via': ['1.1 Caddy']}
        rows.append(json.dumps(row) + '\n')
    write(home, rows)
    assert result(home)['five']['errors'] == len(errors)


@pytest.mark.parametrize('failure', ['failure', 'unreadable'])
@pytest.mark.parametrize('minutes', [35, 120])
def test_unknown_observation_cannot_resolve_or_remind(home, failure, minutes):
    state = traffic.empty_state()
    conditions = {'total_volume': {'count': 10000}}
    traffic.advance(state, conditions, STAMP)
    active = state['incidents']['total_volume'][0]
    active['last_sent'] = STAMP
    # Clearing had started before observation was lost; it must be reset.
    traffic.advance(state, {}, STAMP + 300)
    assert active['clear_since'] is not None
    for offset in range(600, minutes * 60 + 1, 300):
        value = {'failure': True} if failure == 'failure' else dict(result(home), unreadable=True)
        _, alerts, _ = traffic.prepare(state, STAMP + offset, value)
        assert active['resolved'] is None and active['clear_since'] is None
        assert not any('total_volume' in text for _, _, text in alerts)
    recovered = STAMP + minutes * 60 + 300
    for offset in (0, 300, 900, 1799):
        _, alerts, _ = traffic.prepare(state, recovered + offset, result(home))
        assert not any('total_volume resolved' in text for _, _, text in alerts)
    _, alerts, _ = traffic.prepare(state, recovered + 1800, result(home))
    item = next((r, phase) for r, phase, text in alerts if 'total_volume resolved' in text)
    assert item[1] == 'resolved'
    item[0]['recovery_sent'] = recovered + 1800
    _, alerts, _ = traffic.prepare(state, recovered + 2100, result(home))
    assert not any('total_volume resolved' in text for _, _, text in alerts)


def test_unreadable_positive_lower_bounds_can_start_and_remind(home):
    state = traffic.empty_state()
    value = result(home)
    value['unreadable'] = True
    value['five']['total'] = value['five']['largest_source'] = 10000
    _, alerts, _ = traffic.prepare(state, STAMP, value)
    for name in ('total_volume', 'source_volume'):
        record, phase, _ = next(item for item in alerts if name + ' started' in item[2])
        assert phase == 'started'
        record['last_sent'] = STAMP
    _, alerts, _ = traffic.prepare(state, STAMP + 3600, value)
    assert sum('continuing' in text for _, _, text in alerts) == 2


def separated_logs(home):
    write(home, [line()] * 10000)
    boundary = home / 'logs/access-2026-10-29T23-00-00.000-size.log.gz'
    yesterday = home / 'logs/access-2026-10-29T12-00-00.000-size.log.gz'
    with gzip.open(boundary, 'wt') as stream:
        stream.write(line(STAMP - 4000))
    with gzip.open(yesterday, 'wt') as stream:
        stream.writelines(line(STAMP - 45000 - offset) for offset in range(60))
    return yesterday


def test_daily_capacity_failure_keeps_recent_alerts_and_episodes(home, monkeypatch):
    yesterday = separated_logs(home)
    monkeypatch.setattr(traffic, 'DAILY_MAX_KEYS', 50)
    with pytest.raises(RuntimeError, match='capacity'):
        traffic.analyze(home, STAMP, daily=True)
    messages = traffic_setup(home, monkeypatch)
    def worker(home, stamp, logs=None, daily=False):
        try:
            return traffic.analyze(home, stamp, logs, daily=daily)
        except Exception:
            return {'failure': True}
    monkeypatch.setattr(traffic, 'run_analysis', worker)
    monkeypatch.setattr(notify, 'analyze_traffic', lambda home, now: traffic.analyze(home, now.timestamp()))
    assert notify.traffic_notifications(home, 'not-real', NOW)
    assert any('total_volume started' in m['text'] for m in messages)
    assert any('source_volume started' in m['text'] for m in messages)
    assert any('analysis_failed started' in m['text'] for m in messages)
    for minutes in (35, 65, 120):
        write(home, [line(STAMP + minutes * 60)] * 10000)
        assert notify.traffic_notifications(home, 'not-real', NOW + timedelta(minutes=minutes))
    assert not any('total_volume resolved' in m['text'] for m in messages)
    state = json.loads((home / 'host-state/traffic-state.json').read_text())
    assert state['daily_sent'] is None  # Failure remains due for retry.
    assert state['incidents']['total_volume'][-1]['resolved'] is None
    assert_private(messages)


@pytest.mark.parametrize('sent', [False, True])
def test_daily_files_only_open_while_summary_is_due(home, monkeypatch, sent):
    yesterday = separated_logs(home)
    state = traffic.empty_state()
    if sent:
        state['daily_sent'] = traffic.previous_day(STAMP)
    (home / 'host-state/traffic-state.json').write_text(json.dumps(state))
    messages = traffic_setup(home, monkeypatch)
    opened = []
    original = traffic.os.open
    def record_open(path, *args, **kwargs):
        opened.append(Path(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(traffic.os, 'open', record_open)
    assert notify.traffic_notifications(home, 'not-real', NOW)
    assert (yesterday in opened) is not sent
    if sent:
        assert all('daily summary' not in m['text'] for m in messages)
    else:
        assert any('daily summary' in m['text'] for m in messages)
    # The root-terminal preview follows the same scope and never writes state.
    before = (home / 'host-state/traffic-state.json').read_bytes()
    opened.clear()
    traffic.dry_run(home, STAMP, None)
    assert yesterday not in opened
    assert (home / 'host-state/traffic-state.json').read_bytes() == before


def test_hour_boundary_file_is_read_but_older_day_file_is_not(home, monkeypatch):
    yesterday = separated_logs(home)
    write(home, [line()])
    boundary = home / 'logs/access-2026-10-29T23-06-00.000-size.log.gz'
    with gzip.open(boundary, 'wt') as stream:
        stream.write(line(STAMP - 3599) + line(STAMP - 3600) + line(STAMP - 3600.001))
    opened = []
    original = traffic.os.open
    def record_open(path, *args, **kwargs):
        opened.append(Path(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(traffic.os, 'open', record_open)
    measured = result(home)
    assert measured['hour']['total'] == 3
    assert boundary in opened and yesterday not in opened


def test_daily_exception_does_not_suppress_current_thresholds(home, monkeypatch):
    write(home, [line()] * 10000)
    messages = traffic_setup(home, monkeypatch)
    def daily_failure(*args, **kwargs):
        raise TimeoutError('198.51.100.77 /canary-path-7f3a')
    monkeypatch.setattr(traffic, 'run_analysis', daily_failure)
    assert notify.traffic_notifications(home, 'not-real', NOW)
    assert any('total_volume started' in m['text'] for m in messages)
    assert any('analysis_failed started' in m['text'] for m in messages)
    assert_private(messages)


def test_daily_failure_is_not_missing_recent_observation(home):
    state = traffic.empty_state()
    traffic.advance(state, {'total_volume': {'count': 10000}}, STAMP)
    active = state['incidents']['total_volume'][0]
    active['last_sent'] = STAMP
    traffic.prepare(state, STAMP + 300, result(home), {'failure': True})
    assert active['clear_since'] == STAMP + 300
    _, alerts, _ = traffic.prepare(state, STAMP + 2100, result(home), {'failure': True})
    assert any('total_volume resolved' in text for _, _, text in alerts)


def test_separate_worker_deadlines_and_service_budget(home, monkeypatch):
    captured = []
    def run(command, **kwargs):
        captured.append((command, kwargs['timeout']))
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])
    monkeypatch.setattr(traffic.subprocess, 'run', run)
    assert traffic.run_analysis(home, STAMP) == {'failure': True}
    assert traffic.run_analysis(home, STAMP, daily=True) == {'failure': True}
    assert captured[0][1] == 20 and '--daily' not in captured[0][0]
    assert captured[1][1] == 15 and '--daily' in captured[1][0]
    # Seven existing operational alerts, five contacts, three traffic posts.
    assert 7 * 5 + 5 * 5 + traffic.ANALYSIS_SECONDS + traffic.DAILY_ANALYSIS_SECONDS + traffic.TRAFFIC_BATCH * 5 == 110


@pytest.mark.parametrize('boundary_error', ['invalid', 'unreadable'])
def test_bad_boundary_does_not_open_older_day_files(home, monkeypatch, boundary_error):
    yesterday = separated_logs(home)
    boundary = home / 'logs/access-2026-10-29T23-00-00.000-size.log.gz'
    if boundary_error == 'invalid':
        with gzip.open(boundary, 'wt') as stream:
            stream.write('{\n')
    opened = []
    original = traffic.os.open
    def record_open(path, *args, **kwargs):
        opened.append(Path(path))
        if Path(path) == boundary and boundary_error == 'unreadable':
            raise PermissionError('synthetic unreadable log')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(traffic.os, 'open', record_open)
    value = result(home)
    assert value['five']['total'] == 10000
    assert boundary in opened and yesterday not in opened
    assert value['unreadable'] is (boundary_error == 'unreadable')
