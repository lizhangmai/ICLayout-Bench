"""Purpose-based retention with byte-exact, portable compressed evidence reads.

The local objects are hard links, never pointers to a shared external directory.
Each archive remains independently copyable. The shared pool only avoids storing
the same compressed bytes repeatedly on the local filesystem.
"""

import argparse
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import zstandard

from benchmarking.files import (
    EvidenceError,
    atomic_write,
    read_file,
    relative,
    sync_directory,
    write_json,
)
from benchmarking.results.objects import FileObjects, verify_compressed

SCHEMA = 'retained-evidence-v1'
MANIFEST = '.retained/manifest.json'
MIN_BYTES = 64 * 1024


class EvidenceUnavailable(EvidenceError):
    """A recorded attachment was explicitly omitted by the retention policy."""


@lru_cache(maxsize=64)
def _manifest(path, modified, size):
    value = json.loads(Path(path).read_bytes())
    if value.get('schema') != SCHEMA:
        raise EvidenceError('Unsupported retained evidence manifest')
    return value


def _load(root):
    path = root / MANIFEST
    if path.resolve() != path or not path.is_file():
        raise EvidenceError('Invalid retained evidence manifest')
    info = path.stat()
    return _manifest(str(path), info.st_mtime_ns, info.st_size)


def _object(root, record):
    sha, size = record.get('sha256'), record.get('bytes')
    if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
            or type(size) is not int or size < 0 or record.get('codec') != 'zstd'):
        raise EvidenceError('Invalid retained object reference')
    return root / '.retained/objects' / sha[:2] / (sha + '.zst')


def read_retained_file(path):
    """Resolve a missing logical file only through an explicit local manifest."""
    path = Path(path).absolute()
    for parent in path.parents:
        marker = parent / MANIFEST
        if not marker.exists():
            continue
        manifest = _load(parent)
        name = relative(path.relative_to(parent).as_posix(), 'retained file')
        if name in manifest.get('omitted', {}):
            reason = manifest['omitted'][name]['reason']
            raise EvidenceUnavailable(f'{name}: {reason}')
        record = manifest.get('files', {}).get(name)
        if record is not None:
            try:
                return verify_compressed(_object(parent, record), record['sha256'], record['bytes'], collect=True)
            except (OSError, ValueError, zstandard.ZstdError) as error:
                raise EvidenceError('Invalid compressed result evidence: ' + name) from error
    raise FileNotFoundError(path)


def _terminal(root):
    for name, field, expected in (('run.json', 'phase', 'finished'), ('result.json', 'state', 'finished')):
        path = root / name
        if path.is_file():
            if json.loads(path.read_bytes()).get(field) != expected:
                raise ValueError('Only terminal archives can be compacted')
            return
    raise ValueError('Only terminal archives can be compacted')


def _identity(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {'sha256': digest.hexdigest(), 'bytes': size}


def process_omissions(report):
    """Return attachments unnecessary for replaying an ordinary successful check."""
    # A successful simulator can still produce a functional rejection. Keep
    # all raw attachments for rejected, erroneous or ambiguous checks.
    # specs_pass=None also represents an absent spec gate. Overall success and
    # explicit job/metric states distinguish that case from unknown evidence.
    if (report.get('task_success') is not True or report.get('physical_valid') is not True
                or report.get('specs_pass') is False
                or any(job.get('status') != 'passed' for job in report.get('jobs', {}).values())
                or any(metric.get('status') != 'passed'
                       for metric in report.get('metrics', {}).values())):
        return {}
    protected = {ref['path'] for ref in [report.get('plan', {}), *report.get('inputs', {}).values()]
                 if ref.get('path')}
    removable = {}
    for job in report.get('jobs', {}).values():
        for group in ('outputs', 'evidence'):
            for name, ref in job.get(group, {}).items():
                path = ref.get('path')
                if not path:
                    continue
                relative(path, 'attachment path')
                temporary = (name.startswith('results/')
                             or name.endswith(('.raw', '.tran', '.ac', '.dc', '.log', '.db', '.lvsdb'))
                             or name in {'console', 'stdout', 'stderr'})
                if temporary:
                    removable[path] = ref
                else:
                    protected.add(path)
    return {path: ref for path, ref in removable.items() if path not in protected}


def _prunable(root, keep_checks):
    candidates = {}
    for check in sorted((root / 'feedback').glob('check-*')):
        if check.name in keep_checks:
            continue
        try:
            report = json.loads(read_file(check, 'report.json'))
        except FileNotFoundError:
            continue
        for name, ref in process_omissions(report).items():
            candidates[(check / name).relative_to(root).as_posix()] = ref
    return candidates


def _sources(root):
    for base, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(base) / name
            if path.is_symlink():
                raise EvidenceError('Symlink in retained archive: ' + str(path))
            if name in {'.retained', '.runtime', '.private', '__pycache__', '.objects'}:
                directories.remove(name)
        for name in files:
            path = Path(base) / name
            if path.is_symlink():
                raise EvidenceError('Symlink in retained archive: ' + str(path))
            if name.startswith('.') or name.endswith('.lock'):
                continue
            yield path


def inventory(root, *, keep_checks=()):
    """Classify without mutation; unknown attachments are retained conservatively."""
    root = Path(os.path.abspath(root))
    _terminal(root)
    omitted = _prunable(root, set(keep_checks))
    files = []
    for path in _sources(root):
        name, size = path.relative_to(root).as_posix(), path.stat().st_size
        action = ('omit' if name in omitted else 'compress' if size >= MIN_BYTES
                  and not name.startswith('tool-artifacts/')
                  and name not in {'run.json', 'result.json'} and path.suffix not in {'.gds', '.png'}
                  and not (path.suffix == '.json' and size < 16 * 1024 * 1024) else 'keep')
        files.append({'path': name, 'bytes': size, 'action': action})
    return {'schema': SCHEMA, 'root': str(root), 'files': files,
            'prunable_bytes': sum(f['bytes'] for f in files if f['action'] == 'omit'),
            'compressible_bytes': sum(f['bytes'] for f in files if f['action'] == 'compress'),
            'preserved_bytes': sum(f['bytes'] for f in files if f['action'] == 'keep')}


def _validate_sources(root):
    """Reject already incomplete archives before permitting any cleanup."""
    if (root / 'result.json').is_file():
        result = json.loads((root / 'result.json').read_bytes())
        for name in result.get('files', []):
            relative(name, 'result attachment')
            if name == 'layout.png':
                continue
            path = root / name
            if not path.is_file():
                read_retained_file(path)
    reports = [*sorted((root / 'feedback').glob('check-*/report.json'))]
    if (root / 'run.json').is_file() and (root / 'evaluation/report.json').is_file():
        reports.append(root / 'evaluation/report.json')
    for path in reports:
        report = json.loads(path.read_bytes())
        allowed = process_omissions(report) if path.parent.parent.name == 'feedback' else {}
        references = [report.get('plan', {}), *report.get('inputs', {}).values()]
        for job in report.get('jobs', {}).values():
            for group in ('outputs', 'evidence'):
                references.extend(job.get(group, {}).values())
        for ref in references:
            if not ref.get('path'):
                continue
            name = relative(ref['path'], 'evaluation attachment')
            source = path.parent / name
            if source.is_symlink() or (source.exists() and source.resolve() != source):
                raise EvidenceError('Symlink evaluation attachment')
            if source.is_file():
                if source.stat().st_size != ref.get('bytes'):
                    raise EvidenceError('Evaluation attachment size mismatch: ' + name)
            else:
                try:
                    read_retained_file(source)
                except EvidenceUnavailable:
                    if name not in allowed:
                        raise


def verify_archive(root):
    """Verify every unique compressed object and any pending original copies."""
    root = Path(os.path.abspath(root))
    manifest = _load(root)
    seen = set()
    for name, record in manifest['files'].items():
        relative(name, 'retained file')
        key = (record['sha256'], record['bytes'])
        if key not in seen:
            try:
                verify_compressed(_object(root, record), *key)
            except (OSError, ValueError, zstandard.ZstdError) as error:
                raise EvidenceError('Compressed evidence verification failed: ' + name) from error
            seen.add(key)
        source = root / name
        if source.exists() and _identity(source) != {k: record[k] for k in ('sha256', 'bytes')}:
            raise EvidenceError('Original evidence changed: ' + name)
    return {'objects': len(seen), 'files': len(manifest['files']), 'omitted': len(manifest['omitted'])}


def _inherit_objects(root, manifest):
    """Make nested archives independent of any compressed parent representation."""
    verified = set()
    for parent in root.parents:
        if not (parent / MANIFEST).is_file():
            continue
        inherited = _load(parent)
        prefix = root.relative_to(parent).as_posix() + '/'
        for group in ('files', 'omitted'):
            for name, record in inherited.get(group, {}).items():
                if not name.startswith(prefix):
                    continue
                local = relative(name[len(prefix):], 'nested archive file')
                if local in manifest['files'] or local in manifest['omitted']:
                    continue
                if group == 'files':
                    source = _object(parent, record)
                    target = _object(root, record)
                    if record['sha256'] not in verified:
                        verify_compressed(source, record['sha256'], record['bytes'])
                        verified.add(record['sha256'])
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if not target.exists():
                        os.link(source, target)
                        sync_directory(target.parent)
                        sync_directory(target.parent.parent)
                manifest[group][local] = dict(record)


def compact(root, *, objects=None, keep_checks=()):
    """Stage, verify and commit retention before deleting any original file.

    The caller owns the case/service lease and must stop its writers first.
    Re-running after an interruption verifies and finishes the same transaction.
    """
    root = Path(os.path.abspath(root))
    plan = inventory(root, keep_checks=keep_checks)
    _validate_sources(root)
    records = {name: _identity(root / name) for name in ('run.json', 'result.json') if (root / name).is_file()}
    manifest = (json.loads((root / MANIFEST).read_bytes()) if (root / MANIFEST).exists()
                else {'schema': SCHEMA, 'policy': 'final-and-diagnostics-v1', 'files': {}, 'omitted': {}})
    _inherit_objects(root, manifest)
    if any(Path(name).parts[1] in keep_checks for name in manifest['omitted']):
        raise EvidenceUnavailable('A pinned check was already omitted; original bytes are unavailable')
    pending, omitted = [], _prunable(root, set(keep_checks))
    for item in plan['files']:
        path = root / item['path']
        if (item['action'] == 'keep' and not item['path'].startswith('tool-artifacts/')
                and re.fullmatch('[0-9a-f]{64}', path.name)
                and _identity(path)['sha256'] != path.name):
            raise EvidenceError('Content-addressed evidence changed: ' + item['path'])
    # Validate omissions before writing the manifest. A corrupt source never
    # becomes an apparently legitimate policy omission.
    for item in plan['files']:
        if item['action'] != 'omit':
            continue
        identity = _identity(root / item['path'])
        expected = omitted[item['path']]
        if identity != {key: expected.get(key) for key in ('sha256', 'bytes')}:
            raise EvidenceError('Process attachment identity mismatch: ' + item['path'])
        manifest['omitted'][item['path']] = dict(identity, reason='successful_process_check')
        pending.append(item['path'])
    store = FileObjects(objects or root / '.retained/objects')
    for item in plan['files']:
        if item['action'] != 'compress':
            continue
        source = root / item['path']
        sha, size, packed = store.compress_file(source)
        if re.fullmatch('[0-9a-f]{64}', source.name) and sha != source.name:
            raise EvidenceError('Content-addressed evidence changed: ' + item['path'])
        target = root / '.retained/objects' / sha[:2] / (sha + '.zst')
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not target.exists():
            try:
                os.link(packed, target)
                sync_directory(target.parent)
                sync_directory(target.parent.parent)
            except OSError as error:
                # Explicit pools must share the filesystem; silently copying
                # here would hide the loss of cross-run deduplication.
                raise ValueError('Archive and object pool must share a filesystem') from error
        verify_compressed(target, sha, size)
        manifest['files'][item['path']] = {'sha256': sha, 'bytes': size, 'codec': 'zstd'}
        pending.append(item['path'])
    (root / '.retained').mkdir(exist_ok=True, mode=0o700)
    for name, identity in records.items():
        if _identity(root / name) != identity:
            raise EvidenceError('Terminal record changed during archival: ' + name)
    manifest['records'] = records
    write_json(root / MANIFEST, manifest)
    verify_archive(root)
    removed = 0
    # Include originals left behind by a crash after the manifest commit.
    for name in dict.fromkeys([*pending, *manifest['files'], *manifest['omitted']]):
        source = root / name
        if not source.exists():
            continue
        record = manifest['files'].get(name) or manifest['omitted'][name]
        if _identity(source) != {k: record[k] for k in ('sha256', 'bytes')}:
            raise EvidenceError('Evidence changed before removal: ' + name)
        source.unlink()
        removed += 1
    return {'removed_files': removed, **verify_archive(root)}


def compact_service(store, *, objects=None):
    """Seal stopped service evidence; active stores retain their recovery data."""
    from benchmarking.execution.leases import BatchLease

    store = Path(store)
    results = []
    if not store.exists():
        return results
    with BatchLease(store):
        for path in sorted(store.glob('*/run/run.json')):
            if json.loads(path.read_bytes()).get('phase') == 'finished':
                results.append(compact(path.parent, objects=objects))
                _retire_http(path.parent)
    return results


def _retire_http(root):
    """Keep closed-session observations while discarding its authentication state."""
    source = root.parent / 'http.json'
    if not source.exists():
        return False
    raw = source.read_bytes()
    metadata = json.loads(raw)
    secrets = {metadata.get('token'), (metadata.get('creation_response') or {}).get('session_token')}
    sanitized = raw
    for secret in sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
        sanitized = sanitized.replace(secret.encode(), b'<REDACTED>')
    snapshot = json.loads(sanitized)
    if metadata.get('token') and snapshot.get('token') != '<REDACTED>':
        raise EvidenceError('Unable to redact retired session authentication')
    destination = root / 'service-observations.json'
    if destination.exists() and destination.read_bytes() != sanitized:
        raise EvidenceError('Retired service observations changed')
    if not destination.exists():
        atomic_write(destination, sanitized)
    if destination.read_bytes() != sanitized or source.read_bytes() != raw:
        raise EvidenceError('Service state changed during retirement')
    source.unlink()
    sync_directory(source.parent)
    return True


def retire_services(root):
    """Retire only verified, stopped sessions; unfinished recovery stays intact."""
    from benchmarking.execution.leases import BatchLease

    results = []
    root = Path(os.path.abspath(root))
    for directory, terminal in _archives(root):
        if (not terminal or directory.name != 'run' or directory.parent.parent.name != 'service-store'
                or not (directory / MANIFEST).exists()):
            continue
        entry = {'root': directory.relative_to(root).as_posix()}
        try:
            with BatchLease(directory.parent.parent):
                verify_archive(directory)
                entry['retired'] = _retire_http(directory)
        except (OSError, ValueError, zstandard.ZstdError) as error:
            entry.update(error_type=type(error).__name__)
        results.append(entry)
    return {'retired': sum(row.get('retired', False) for row in results),
            'errors': sum('error_type' in row for row in results), 'records': results}


def _archives(root):
    """Discover terminal record formats, never infer eligibility from age."""
    for base, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories
                          if name not in {'.runtime', '.private', '.retained', '.objects', '__pycache__'}
                          and not (Path(base) / name).is_symlink()]
        directory = Path(base)
        for name, field, state in (('run.json', 'phase', 'finished'), ('result.json', 'state', 'finished')):
            if name not in files:
                continue
            path = directory / name
            if path.is_symlink():
                continue
            try:
                record = json.loads(path.read_bytes())
            except (OSError, ValueError):
                continue
            if not isinstance(record, dict):
                continue
            if name == 'result.json' and record.get('format') != 'participant-result':
                continue
            if field not in record:
                continue
            yield directory, record.get(field) == state and not (directory / '.runtime').exists()


def retain_tree(root, *, apply=False, report=None, keep_checks=()):
    """Inventory or migrate an explicit result scope, preserving incomplete runs."""
    from benchmarking.execution.leases import BatchLease
    from benchmarking.participants.attempt.storage import CaseLease

    root = Path(os.path.abspath(root))
    records = []
    archives = list(_archives(root))
    for index, (directory, terminal) in enumerate(archives):
        entry = {'root': directory.relative_to(root).as_posix()}
        if not terminal:
            entry['status'] = 'protected_unfinished'
            records.append(entry)
            continue
        try:
            if not apply:
                entry.update(inventory(directory, keep_checks=keep_checks), status='planned')
                entry['root'] = directory.relative_to(root).as_posix()
            else:
                lease = (BatchLease(directory.parent.parent) if directory.name == 'run'
                         and directory.parent.parent.name == 'service-store' else CaseLease(directory))
                with lease:
                    entry.update(compact(directory, objects=root / '.objects', keep_checks=keep_checks),
                                 status='compacted')
            records.append(entry)
        except (OSError, ValueError, zstandard.ZstdError) as error:
            # Store paths and exception classes, never arbitrary tool/auth output.
            entry.update(status='protected_error', error_type=type(error).__name__, reason=str(error))
            records.append(entry)
        if apply and (index + 1) % 10 == 0:
            print(json.dumps({'completed': index + 1, 'total': len(archives)}), flush=True)
            if report:
                write_json(Path(report), {'schema': SCHEMA, 'records': records})
    summary = {'archives': len(records),
               'compacted': sum(row['status'] == 'compacted' for row in records),
               'protected_unfinished': sum(row['status'] == 'protected_unfinished' for row in records),
               'protected_error': sum(row['status'] == 'protected_error' for row in records),
               'prunable_bytes': sum(row.get('prunable_bytes', 0) for row in records),
               'compressible_bytes': sum(row.get('compressible_bytes', 0) for row in records)}
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        write_json(Path(report), {'schema': SCHEMA, 'summary': summary, 'records': records})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='One terminal run archive')
    parser.add_argument('--objects', type=Path, help='Shared compressed object pool on the same filesystem')
    parser.add_argument('--apply', action='store_true', help='Commit verified retention and remove original copies')
    parser.add_argument('--verify', action='store_true', help='Verify an already compacted archive')
    parser.add_argument('--keep-check', action='append', default=[])
    parser.add_argument('--tree', action='store_true', help='Process terminal archives in one explicit result scope')
    parser.add_argument('--report', type=Path, help='Write the full inventory or migration receipt')
    parser.add_argument('--retire-services', action='store_true', help='Retire verified closed-session authentication')
    args = parser.parse_args(argv)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.retire_services:
        if not args.apply:
            parser.error('--retire-services requires --apply')
        result = retire_services(args.root)
        if args.report:
            write_json(args.report, result)
    elif args.tree:
        result = retain_tree(args.root, apply=args.apply, report=args.report, keep_checks=args.keep_check)
    elif args.verify:
        result = verify_archive(args.root)
    elif args.apply:
        from benchmarking.execution.leases import BatchLease
        from benchmarking.participants.attempt.storage import CaseLease

        root = Path(os.path.abspath(args.root))
        lease = (BatchLease(root.parent.parent) if root.name == 'run'
                 and root.parent.parent.name == 'service-store' else CaseLease(root))
        with lease:
            result = compact(root, objects=args.objects, keep_checks=args.keep_check)
    else:
        result = inventory(args.root, keep_checks=args.keep_check)
    print(json.dumps(result, indent=2))
    return int(bool(result.get('protected_error') or result.get('errors')))


if __name__ == '__main__':
    raise SystemExit(main())
