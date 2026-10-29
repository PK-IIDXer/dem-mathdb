"""Host-only, count-only traffic monitoring. Python 3.12, standard library only.

Addresses and raw-row digests exist only inside analyze(). They are never
returned, persisted, printed or passed to the notification transport.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

WINDOW = 300
API_ERRORS = 10
RATE_LIMITED = 300
SOURCE_VOLUME = 3000
TOTAL_VOLUME = 10000
WRITES_TOTAL = 500
WRITES_SOURCE = 150
INVALID_ROWS = 20
REMINDER = 3600
RECOVERY = 1800
ANALYSIS_SECONDS = 20
DAILY_ANALYSIS_SECONDS = 15
MAX_LINE = 64 * 1024
MAX_KEYS = 200000
DAILY_MAX_KEYS = 250000
TRAFFIC_BATCH = 3  # At most 15s of delivery, after contacts and independent 20s / 15s analyses.
KINDS = ('api_errors', 'rate_limited', 'source_volume', 'total_volume', 'writes', 'log_unreadable', 'analysis_failed')
CATEGORIES = ('read', 'write', 'heavy', 'export', 'forbidden', 'static', 'contact')
PURE_POSTS = {'/formulas/parse', '/formulas/print'}
HEAVY = {
    '/proofs/{id}/steps/suggest': 'POST', '/proofs/{id}/steps/suggest-backward': 'POST',
    '/theorems/applicable': 'GET', '/proofs/{id}/validate': 'POST', '/formulas/search': 'POST',
    '/formulas/validate': 'POST', '/proofs/compute-substituted-tokens': 'POST',
    '/proofs/compute-gen-tokens': 'POST', '/workspace/export': 'GET',
    '/proofs/{id}/is-valid-in-system/{axiom_system_id}': 'GET',
}
HEAVY_PATTERNS = [(re.compile('^' + re.sub(r'\{[^}]+\}', '[^/]+', path) + '$'), method) for path, method in HEAVY.items()]
DOCS = {'/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect'}
PROBES = ('/.env', '/.git', '.aws', 'wp-', 'phpmyadmin', 'cgi-bin', 'actuator', 'server-status', '.php')
ROTATED = re.compile(r'access-(\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)(?:\.\d+)?(?:-size)?\.log(?:\.gz)?\Z|access\.log-\d{8}(?:\.gz)?\Z|access\.log\.\d+(?:\.gz)?\Z')
NUMERIC_KEYS = ('total', 'sources', 'limited', 'errors', 'writes', 'largest_source', 'largest_writer', 'probing', 'probing_sources')


def utc(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def classify(method, uri):
    path = unquote(urlsplit(uri).path)
    if path[:4].lower() != '/api' or (len(path) > 4 and path[4] != '/'):
        return 'static', False, False, False
    path = path[4:] or '/'
    kind = 'read' if method in {'GET', 'HEAD', 'OPTIONS'} or (method == 'POST' and path in PURE_POSTS) else 'write'
    if method == 'POST' and path == '/contact':
        kind = 'contact'
    heavy = any(method == verb and regex.fullmatch(path) for regex, verb in HEAVY_PATTERNS)
    export = method == 'GET' and path == '/workspace/export'
    forbidden = export or (method == 'POST' and path == '/symbol-roles') or (method in {'GET', 'HEAD'} and path in DOCS)
    return kind, heavy, export, forbidden


MAINTENANCE_DETAILS = ('Beta is under maintenance', 'Beta write state: maintenance')
MAINTENANCE_LENGTHS = {len(json.dumps({'detail': text, 'code': 'beta.maintenance'}, separators=(',', ':')).encode()) for text in MAINTENANCE_DETAILS}


def maintenance_response(headers):
    # API errors have deterministic short JSON bodies, below GZip's 1024-byte
    # minimum. Retain all unknown 503s, Retry-After errors and plain-text 503s.
    lowered = {key.lower(): value for key, value in headers.items() if isinstance(key, str)}
    def single(key):
        value = lowered.get(key)
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        return value if isinstance(value, str) else ''
    length = single('content-length')
    return (single('content-type').split(';')[0].strip().lower() == 'application/json'
            and length.isascii() and length.isdigit() and int(length) in MAINTENANCE_LENGTHS
            and not lowered.get('retry-after') and not lowered.get('content-encoding'))


class Bucket:
    def __init__(self, start, end, max_keys=MAX_KEYS):
        self.start, self.end, self.max_keys = start, end, max_keys
        self.total = self.limited = self.errors = self.writes = self.probing = 0
        self.sources, self.writers, self.classes = Counter(), Counter(), Counter()
        self.categories, self.origins, self.probers = Counter(), Counter(), set()

    def add(self, stamp, status, address, method, uri, proxied, frozen, maintenance):
        if not self.start <= stamp <= self.end:
            return
        kind, heavy, export, forbidden = classify(method, uri)
        self.total += 1
        self.sources[address] += 1
        self.classes[str(status // 100) + 'xx'] += 1
        self.categories[kind] += 1
        self.categories['heavy'] += int(heavy)
        self.categories['export'] += int(export)
        self.categories['forbidden'] += int(forbidden)
        self.origins['upstream' if proxied else 'edge_or_unknown'] += 1
        self.limited += int(status == 429)
        self.errors += int(kind != 'static' and status >= 500 and not (frozen and proxied and maintenance and kind == 'write' and status == 503))
        if kind == 'write' and proxied and 200 <= status < 300:
            self.writes += 1
            self.writers[address] += 1
        if any(pattern in unquote(urlsplit(uri).path).lower() for pattern in PROBES):
            self.probing += 1
            self.probers.add(address)
        if len(self.sources) > self.max_keys:
            raise RuntimeError('analysis capacity reached')

    def export(self):
        return dict(total=self.total, sources=len(self.sources), limited=self.limited, errors=self.errors,
                    writes=self.writes, largest_source=max(self.sources.values(), default=0),
                    largest_writer=max(self.writers.values(), default=0), probing=self.probing,
                    probing_sources=len(self.probers), classes={k: self.classes[k] for k in ('1xx', '2xx', '3xx', '4xx', '5xx')},
                    categories={k: self.categories[k] for k in CATEGORIES},
                    origins={k: self.origins[k] for k in ('upstream', 'edge_or_unknown')},
                    top_percent=[round(100 * count / self.total, 2) for count in sorted(self.sources.values(), reverse=True)[:5]])


def discover(home, logs, check, cutoff=None):
    if logs is not None:
        return list(logs), False
    directory = home / 'logs'
    if directory.is_symlink():
        return [], True
    current = directory / 'access.log'
    try:
        candidates = []
        for path in directory.iterdir():
            check()
            if ROTATED.fullmatch(path.name):
                candidates.append(path)
            if len(candidates) > 10000:
                raise RuntimeError('analysis capacity reached')
        # Rotation mtime is the end of the file, not the first request time.
        def rotation_end(path):
            match = ROTATED.fullmatch(path.name)
            if match.group(1):
                return datetime.strptime(match.group(1), '%Y-%m-%dT%H-%M-%S').replace(tzinfo=timezone.utc).timestamp(), path.lstat().st_mtime
            return path.lstat().st_mtime, path.lstat().st_mtime
        candidates.sort(key=rotation_end, reverse=True)
        if cutoff is not None:
            bounded = []
            for path in candidates:
                bounded.append(path)
                if rotation_end(path)[0] < cutoff:
                    break
            candidates = bounded
    except OSError:
        return [], True
    return [current, *candidates], False


def analyze(home, now, logs=None, clock=time.monotonic, seconds=None, daily=False):
    if seconds is None:
        seconds = (DAILY_ANALYSIS_SECONDS if daily else ANALYSIS_SECONDS) - 1
    max_keys = DAILY_MAX_KEYS if daily else MAX_KEYS
    deadline = clock() + seconds
    def check():
        if clock() >= deadline:
            raise TimeoutError('analysis deadline')
    check()
    midnight = math.floor(now / 86400) * 86400
    day_start = midnight - 86400
    cutoff = day_start if daily else now - 3600
    buckets = ([Bucket(day_start, midnight - 0.000001, max_keys)] if daily else
               [Bucket(now - WINDOW, now, max_keys), Bucket(cutoff, now, max_keys)])
    paths, unreadable = discover(home, logs, check, cutoff)
    earliest = None
    invalid = scanned = 0
    seen, inodes = {}, set()
    frozen = (home / 'flags/read_only').exists()
    for index, path in enumerate(paths):
        check()
        local = Counter()
        maximum = None
        new_keys = 0
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or path.is_symlink():
                raise OSError('not a regular log')
            identity = (before.st_dev, before.st_ino)
            if identity in inodes:
                continue
            inodes.add(identity)
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
            try:
                actual = os.fstat(fd)
                if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != identity:
                    raise OSError('log changed')
                with os.fdopen(fd, 'rb', closefd=False) as raw:
                    source = gzip.GzipFile(fileobj=raw) if path.suffix == '.gz' else raw
                    try:
                        while True:
                            check()
                            line = source.readline(MAX_LINE + 1)
                            if not line:
                                break
                            oversized = len(line) > MAX_LINE
                            digest = hashlib.sha256(line)
                            if oversized:
                                while line and not line.endswith(b'\n'):
                                    check()
                                    line = source.readline(MAX_LINE + 1)
                                    digest.update(line)
                            fingerprint = digest.digest()
                            if fingerprint not in local and fingerprint not in seen:
                                new_keys += 1
                            local[fingerprint] += 1
                            if local[fingerprint] <= seen.get(fingerprint, 0):
                                continue
                            if len(seen) + new_keys > max_keys:
                                raise RuntimeError('analysis capacity reached')
                            scanned += 1
                            try:
                                if oversized:
                                    raise ValueError('oversized row')
                                row = json.loads(line)
                                stamp, status = row['ts'], row['status']
                                if (isinstance(stamp, bool) or not isinstance(stamp, (float, int)) or not math.isfinite(stamp)
                                        or stamp >= now + 60 or type(status) is not int or not 100 <= status <= 599):
                                    raise ValueError('invalid fields')
                                req = row['request']
                                address = str(ipaddress.IPv4Address(req['remote_ip'])) if isinstance(req['remote_ip'], str) else None
                                method, uri = req['method'], req['uri']
                                if address is None or not isinstance(method, str) or not isinstance(uri, str) or not uri.startswith('/'):
                                    raise ValueError('invalid fields')
                                # Validate the URI before adding to any bucket.
                                urlsplit(uri)
                                headers = row.get('resp_headers', {})
                                if not isinstance(headers, dict):
                                    raise ValueError('invalid headers')
                                proxied = any(isinstance(key, str) and key.lower() == 'via' and bool(value) for key, value in headers.items())
                                maintenance = status == 503 and frozen and maintenance_response(headers)
                            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
                                invalid += 1
                                continue
                            earliest = stamp if earliest is None else min(earliest, stamp)
                            maximum = stamp if maximum is None else max(maximum, stamp)
                            for bucket in buckets:
                                bucket.add(stamp, status, address, method, uri, proxied, frozen, maintenance)
                    finally:
                        if source is not raw:
                            source.close()
            finally:
                os.close(fd)
        except (OSError, EOFError):
            unreadable = True
        for key, count in local.items():
            seen[key] = max(seen.get(key, 0), count)
        # Include one older boundary file; never assume rows inside it are sorted.
        if logs is None and index > 0 and maximum is not None and maximum < cutoff:
            break
    check()
    if daily:
        return dict(day=buckets[0].export(), invalid_rows=invalid, scanned_rows=scanned, unreadable=unreadable,
                    day_start=day_start, day_end=midnight, covered_from=min(midnight, max(day_start, earliest if earliest is not None else midnight)),
                    partial=unreadable or earliest is None or earliest > day_start)
    return dict(five=buckets[0].export(), hour=buckets[1].export(),
                invalid_rows=invalid, scanned_rows=scanned, unreadable=unreadable)


def findings(result):
    if result.get('failure'):
        return {'analysis_failed': {'count': 1}}
    five, hour = result['five'], result['hour']
    output = {}
    for kind, count, limit in [('api_errors', five['errors'], API_ERRORS), ('rate_limited', five['limited'], RATE_LIMITED),
                               ('source_volume', five['largest_source'], SOURCE_VOLUME), ('total_volume', five['total'], TOTAL_VOLUME)]:
        if count >= limit:
            output[kind] = dict(count=count, total=five['total'], sources=five['sources'])
    if hour['writes'] >= WRITES_TOTAL or hour['largest_writer'] >= WRITES_SOURCE:
        output['writes'] = dict(count=hour['writes'], largest=hour['largest_writer'], sources=hour['sources'])
    if result['unreadable'] or (result['invalid_rows'] >= INVALID_ROWS and result['invalid_rows'] * 100 >= result['scanned_rows']):
        output['log_unreadable'] = dict(count=result['invalid_rows'], total=result['scanned_rows'])
    return output


def empty_state():
    return {'incidents': {kind: [] for kind in KINDS}, 'daily_sent': None, 'days': {}}


def numeric(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10**15:
        raise ValueError('invalid numeric state')
    return value


def clean_counts(value):
    if not isinstance(value, dict) or set(value) - {'count', 'total', 'sources', 'largest'}:
        raise ValueError('invalid count state')
    return {key: numeric(item) for key, item in value.items()}


def load_state(path):
    if not path.exists():
        return empty_state()
    if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('invalid traffic state')
    value = json.loads(path.read_text(encoding='utf-8'))
    if set(value) != {'incidents', 'daily_sent', 'days'} or set(value['incidents']) != set(KINDS):
        raise ValueError('invalid traffic state')
    date = value['daily_sent']
    if date is not None:
        datetime.strptime(date, '%Y-%m-%d')
    for records in value['incidents'].values():
        if not isinstance(records, list) or len(records) > 5000:
            raise ValueError('invalid traffic state')
        for record in records:
            if set(record) != {'started', 'last_sent', 'clear_since', 'resolved', 'recovery_sent', 'counts'}:
                raise ValueError('invalid traffic state')
            clean_counts(record['counts'])
            for key in ('started', 'last_sent', 'clear_since', 'resolved', 'recovery_sent'):
                if record[key] is not None:
                    utc(numeric(record[key]))
    for date, counts in value['days'].items():
        datetime.strptime(date, '%Y-%m-%d')
        if set(counts) - set(KINDS):
            raise ValueError('invalid traffic history')
        for count in counts.values():
            numeric(count)
    return value


def advance(state, conditions, now, observed=None):
    # Unknown is not clear. Recent positive lower bounds remain trustworthy.
    if observed is None:
        observed = not ({'analysis_failed', 'log_unreadable'} & set(conditions))
    known = set(KINDS) if observed else {'analysis_failed', *conditions}
    date = utc(now)[:10]
    oldest = utc(math.floor(now / 86400) * 86400 - 86400)[:10]
    state['days'] = {day: counts for day, counts in state['days'].items() if oldest <= day <= date}
    for kind in KINDS:
        records = state['incidents'][kind]
        records[:] = [r for r in records if r['recovery_sent'] is None or r['resolved'] >= now - 2 * 86400]
        active = records[-1] if records and records[-1]['resolved'] is None else None
        if kind in conditions:
            if active is None:
                active = dict(started=now, last_sent=None, clear_since=None, resolved=None, recovery_sent=None, counts={})
                records.append(active)
                history = state['days'].setdefault(date, {})
                history[kind] = history.get(kind, 0) + 1
            active['clear_since'] = None
            active['counts'] = clean_counts(conditions[kind])
        elif active is not None and kind not in known:
            active['clear_since'] = None
        elif active is not None:
            if active['clear_since'] is None:
                active['clear_since'] = now
            if now - active['clear_since'] >= RECOVERY:
                active['resolved'] = now
    return known


def guide(minutes):
    return ('\nInspect counts in a root interactive terminal with:\n'
            f'python3 deploy/beta/access_log.py summary --minutes {minutes}')


def alert_text(kind, record, phase, now):
    # Only fixed words and validated numbers/times cross this boundary.
    counts = clean_counts(record['counts'])
    text = f'Beta traffic: {kind} {phase}\nUTC: {utc(now)}\nStarted UTC: {utc(record["started"])}'
    for key in ('count', 'total', 'sources', 'largest'):
        if key in counts:
            text += f'\n{key}: {counts[key]}'
    if kind == 'analysis_failed':
        text += '\nAnalysis stopped before completion.'
    return text + guide(60 if kind == 'writes' else 5)


def pending(state, now, known=None):
    result = []
    for kind in KINDS:
        if known is not None and kind not in known:
            continue
        for record in state['incidents'][kind]:
            phase = None
            if record['last_sent'] is None:
                phase = 'started'
            elif record['resolved'] is not None and record['recovery_sent'] is None:
                phase = 'resolved'
            elif record['resolved'] is None and record['clear_since'] is None and now - record['last_sent'] >= REMINDER:
                phase = 'continuing'
            if phase:
                result.append((record, phase, alert_text(kind, record, phase, now)))
    return result


def daily_text(result, state):
    day = result['day']
    text = f'Beta traffic: daily summary\nUTC: {utc(result["day_start"])} to {utc(result["day_end"])}'
    text += f'\nCoverage from UTC: {utc(result["covered_from"])}; ' + ('partially missing' if result['partial'] else 'complete')
    for key in NUMERIC_KEYS:
        text += f'\n{key}: {numeric(day[key])}'
    for name in ('classes', 'categories'):
        allowed = ('1xx', '2xx', '3xx', '4xx', '5xx') if name == 'classes' else CATEGORIES
        text += '\n' + name + ': ' + ', '.join(f'{key}={numeric(day[name][key])}' for key in allowed)
    text += '\nTop five source shares: ' + ', '.join(f'{numeric(value):.2f}%' for value in day['top_percent'][:5])
    date = utc(result['day_start'])[:10]
    text += '\nIncidents: ' + ', '.join(f'{kind}={numeric(state["days"].get(date, {}).get(kind, 0))}' for kind in KINDS)
    return text + guide(1440)


def run_analysis(home, now, logs=None, daily=False):
    try:
        command = [sys.executable, '-I', '-B', str(Path(__file__)), 'analyze', '--home', str(home),
                   '--now', datetime.fromtimestamp(now, timezone.utc).isoformat()]
        if daily:
            command.append('--daily')
        for path in logs or []:
            command += ['--log', str(path)]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=DAILY_ANALYSIS_SECONDS if daily else ANALYSIS_SECONDS, check=False)
        if process.returncode or len(process.stdout) > 65536:
            return {'failure': True}
        value = json.loads(process.stdout)
        return value if isinstance(value, dict) else {'failure': True}
    except Exception:
        return {'failure': True}


def previous_day(now):
    return utc(math.floor(now / 86400) * 86400 - 86400)[:10]


def prepare(state, now, result, day_result=None):
    conditions = findings(result)
    observed = not (result.get('failure') or result.get('unreadable'))
    summary = None
    if day_result is not None:
        try:
            if day_result.get('failure'):
                raise ValueError('daily analysis incomplete')
            summary = daily_text(day_result, state)
        except Exception:
            conditions['analysis_failed'] = {'count': 1}
    known = advance(state, conditions, now, observed=observed)
    alerts = pending(state, now, known)
    return conditions, alerts, summary


def dry_run(home, now, logs):
    state = load_state(home / 'host-state/traffic-state.json')
    result = run_analysis(home, now, logs)
    day_result = run_analysis(home, now, logs, daily=True) if state['daily_sent'] != previous_day(now) else None
    conditions, alerts, summary = prepare(state, now, result, day_result)
    texts = [text for _, _, text in alerts]
    if summary is not None:
        texts.append(summary)
    return dict(counts=result, daily_counts=day_result, findings=conditions, notifications=texts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('analyze', 'dry-run'))
    parser.add_argument('--home', type=Path, default=Path('/var/lib/dem-beta'))
    parser.add_argument('--log', action='append', type=Path)
    parser.add_argument('--now')
    parser.add_argument('--daily', action='store_true', help='Internal: aggregate yesterday in a separate worker')
    args = parser.parse_args()
    try:
        instant = datetime.now(timezone.utc) if args.now is None else datetime.fromisoformat(args.now.replace('Z', '+00:00'))
        if instant.tzinfo is None:
            raise ValueError('UTC offset required')
        now = instant.timestamp()
        if args.command == 'dry-run':
            if getattr(os, 'geteuid', lambda: -1)() != 0 or not sys.stdout.isatty():
                raise PermissionError('root interactive terminal required')
            result = dry_run(args.home, now, args.log)
        else:
            result = analyze(args.home, now, args.log, daily=args.daily)
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception:
        print('{"failure": true}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
