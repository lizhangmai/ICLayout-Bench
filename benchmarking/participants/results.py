"""Small terminal results; live recovery material remains in .runtime until export commits."""
import hashlib
import json
import re
import shutil
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import quote

from benchmarking.engine.recorder import BatchLease
from benchmarking.files import atomic_write, read_file

from .runner import save


def load(path):
    return json.loads(path.read_text())


def checked(root, ref):
    raw = read_file(root, ref['path'])
    if hashlib.sha256(raw).hexdigest() != ref['sha256'] or ('bytes' in ref and len(raw) != ref['bytes']):
        raise ValueError('Result evidence identity mismatch: ' + ref['path'])
    return raw


def put(root, name, raw, files):
    destination = root / name
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists() and destination.read_bytes() != raw:
        raise ValueError('Refusing to replace different result artifact: ' + name)
    if not destination.exists():
        atomic_write(destination, raw)
    if name not in files:
        files.append(name)


def without_hashes(value):
    """Drop redundant structured digests; preserve raw diagnostic text verbatim."""
    if isinstance(value, dict):
        return {k: without_hashes(v) for k, v in value.items()
                if k != 'sha256' and not k.endswith('_sha256') and k != 'public_revision'}
    if isinstance(value, list):
        return [without_hashes(v) for v in value]
    return value


def compact_result(result):
    evaluation_identity = result.get('evaluation') or {}
    original_identity = result["identity"]
    result = without_hashes(result)
    result["identity"] = dict(original_identity)
    # Preserve measurement identities even when reusable file inventories are compacted.
    evaluation = result.get('evaluation')
    if evaluation is not None:
        for key in ('task_sha256', 'condition', 'submission'):
            if key in evaluation_identity:
                evaluation[key] = evaluation_identity[key]
    result['format'] = 'participant-result'
    result['files'] = list(result.get('files', []))
    result.pop('resources', None)
    if 'tool_identity' in evaluation_identity:
        result['evaluation']['tool_identity'] = evaluation_identity['tool_identity']
    result.get('image', {}).pop('image_id', None)
    return result


def compact_report(report):
    report = without_hashes(report)
    for key in ('inputs', 'backends'):
        report.pop(key, None)
    for job in report['jobs'].values():
        for group in ('outputs', 'evidence'):
            job[group] = {k: v for k, v in job[group].items()
                          if 'content' in v or 'path' in v}
    return report


def verify(root, result):
    for name in result.get('files', []):
        if name != 'layout.png':  # A derived image may be regenerated.
            read_file(root, name)


def evaluation_export(source, root, files):
    from benchmarking.evaluation import parse_evaluation
    from benchmarking.scoring import recompute_score

    report = load(source / 'report.json')
    plan_raw = checked(source, report['plan'])
    plan = parse_evaluation(plan_raw, file_format=report['plan']['format'])
    if recompute_score(plan, report) != report.get('score'):
        raise ValueError('Evaluation measurements do not reproduce the stored score')
    put(root, 'evaluation/plan.json', plan_raw, files)
    report['plan']['path'] = 'plan.json'
    # Input bytes and reusable tool/PDK sources belong to preparation, not results.
    for ref in report['inputs'].values():
        ref.pop('path', None)
    for job_id, job in report['jobs'].items():
        retained = {}
        for group in ('outputs', 'evidence'):
            for name, ref in job[group].items():
                path = ref.pop('path', None)
                if path is None:
                    continue
                original = dict(ref, path=path)
                reusable = (':' in name or name in {'runner', 'configuration', 'support_manifest'}
                            or ref['format'] in {'python', 'gds'})
                if reusable:
                    ref['retention'] = 'rebuild_from_recorded_environment'
                    continue
                raw = checked(source, original)
                # Keep readable logs/measurements inline instead of dozens of tiny files.
                if ref['format'] in {'text', 'json', 'spice', 'tcl', 'magic-ext'}:
                    ref['content'] = raw.decode('utf-8')
                else:
                    sha = ref['sha256']
                    if sha not in retained:
                        filename = quote(job_id + '-' + name, safe='-_.')
                        put(root, 'evaluation/' + filename, raw, files)
                        retained[sha] = filename
                    ref['path'] = retained[sha]
    put(root, 'evaluation/report.json', (json.dumps(compact_report(report), indent=2) + '\n').encode(), files)


def traces(source, root, files, prefix=''):
    participant = source / 'participant'
    recovery = participant / '.private/recovery.json'
    secrets = load(recovery).get('redactions', []) if recovery.exists() else []
    def redact(raw):
        for value in sorted(secrets, key=len, reverse=True):
            if value:
                raw = raw.replace(value.encode(), b'<REDACTED>')
        return raw
    paths = sorted(participant.glob('launch-*-harness.jsonl'),
                   key=lambda p: int(p.name.split('-')[1]))
    paths += [participant / 'harness.jsonl']
    raw = b''.join(redact(p.read_bytes()).rstrip(b'\n') + b'\n' for p in paths if p.is_file())
    if raw:
        put(root, prefix + 'agent.jsonl', raw, files)
    stderr = b'\n'.join(redact(p.read_bytes()) for p in sorted(participant.glob('*harness.stderr')))
    return stderr.decode('utf-8', errors='replace')


def report_text(result):
    evaluation = result.get('evaluation') or {}
    summary = result['summary']
    score = evaluation.get('score') or {}
    row = result['identity']['plan'][0]
    lines = [f"# {summary.get('task', evaluation.get('task_id', 'Case'))}", '',
             f"Model: `{row.get('model')}`; effort: `{row.get('effort')}`; outcome: **{summary.get('outcome')}**.",
             f"Score: **{summary.get('score')}** (reference = 100; uncapped); verification: `{evaluation.get('verification_level', 'unknown')}`.",
             f"Agent time: {result.get('execution', {}).get('elapsed_seconds', 'unknown')} seconds (excludes preparation and evaluation).", '',
             '[Machine-readable result](result.json)', '']
    benchmark = result['identity'].get('benchmark') or {}
    lines += [f"ICLayout-Bench: `{benchmark.get('version') or 'unknown'}`; Git commit: `{benchmark.get('commit') or 'unknown'}`.", '']
    if 'final.gds' in result.get('files', []):
        lines += ['[Submitted GDS](final.gds) · [Layout image](layout.png)', '']
    if score.get('method') == 'layout':
        formula = '`S = 100 × product(q_i ** w_i)` with explicit metric and area weights.'
        lines += ['## Scoring', '', formula, '',
                  'Each metric uses its worst paired source-relative quality. Q is reference area / candidate area. Scores may exceed 100. Errors are unknown; functional rejection is zero.', '',
                  '| Component | Value |', '| --- | ---: |']
        lines += [f'| {key} | {value} |' for key, value in score.get('components', {}).items()]
        area = score.get('area') or {}
        lines += ['', f"Area: {area.get('value')} µm²; reference: {area.get('target')} µm².", '']
    if score.get('method') == 'layout':
        lines += ['### Weights', '', '| Metric | Weight |', '| --- | ---: |']
        lines += [f'| {key} | {weight:.6g} |' for key, weight in score.get('weights', {}).items()]
        lines += ['']
    relative = score.get('method') == 'layout'
    fields = ('value', 'unit', 'lower', 'upper', 'normalization', 'scale', 'status')
    headers = ['Metric', 'Value', 'Unit', 'Lower', 'Upper', 'Normalization', 'Scale', 'Status']
    lines += ['## Measurements', '', '| ' + ' | '.join(headers) + ' |',
              '| ' + ' | '.join('---' for _ in headers) + ' |']
    for key, metric in evaluation.get('metrics', {}).items():
        values = [key] + [str(metric.get(k)) if metric.get(k) is not None else '—' for k in fields]
        lines.append('| ' + ' | '.join(values) + ' |')
    if relative:
        lines += ['', '## Source comparisons', '', '| Metric | Source observations | Quality ratio |',
                  '| --- | --- | ---: |']
        for key, metric in evaluation.get('metrics', {}).items():
            baseline = metric.get('baseline', [])
            if not baseline:
                continue
            observations = []
            for ref in baseline:
                job, name = ref.split(':')
                value = evaluation.get('jobs', {}).get(job, {}).get('measurements', {}).get(name, {}).get('value')
                observations.append(f'{ref} = {value}')
            lines.append(f"| {key} | {'; '.join(observations)} | {score.get('metrics', {}).get(key)} |")
    lines += ['', 'Full individual observations are retained in result.json. Local results cover only the declared case conditions; they are not manufacturing signoff or repeated-run reliability evidence.', '',
              'Reusable PDK/tool sources and native credentials are not retained. Inputs are defined by the recorded ICLayout-Bench release.', '']
    return '\n'.join(lines).encode()


def finish_case(root):
    """Caller owns the case lease. Commit verified outputs before removing runtime state."""
    root = Path(root)
    state = load(root / 'result.json')
    runtime = root / '.runtime'
    if state.get('state') == 'finished':
        if state.get('format') != 'participant-result':
            raise ValueError('Unsupported participant result format')
        verify(root, state)
        if runtime.exists():
            shutil.rmtree(runtime)
        return state['summary']
    summary = load(runtime / 'summary.json')
    if summary.get('state') != 'finished':
        raise ValueError('Cannot finalize an unfinished case')
    # Do not delete stores still owned by a live service, including abandoned attempts.
    with ExitStack() as stack:
        for store in sorted(runtime.rglob('service-store')):
            stack.enter_context(BatchLease(store))
        result = {'format': 'participant-result', 'identity': state['identity'], 'state': 'finalizing',
                  'summary': dict(summary, result='result.json'), 'files': []}
        files = result['files']
        raw_path = runtime / 'participant/analysis/result.json'
        if not raw_path.exists():
            raise ValueError('Terminal service result is missing; runtime retained')
        result['evaluation'] = evaluation = load(raw_path)
        if evaluation.get('state') not in {'complete', 'error'}:
            raise ValueError('Service evaluation is not terminal')
        sid = evaluation['session_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
            raise ValueError('Invalid session ID')
        archive = runtime / 'service/service-store' / sid / 'run'
        if archive.exists():
            recorded = load(archive / 'run.json')
            if evaluation.get('submission'):
                candidate = checked(archive, recorded['candidate'])
                if hashlib.sha256(candidate).hexdigest() != evaluation['submission']['candidate_sha256']:
                    raise ValueError('Final candidate differs from scored submission')
                put(root, 'final.gds', candidate, files)
                task = json.loads(checked(archive, recorded['task']))
                if task['task_sha256'] != evaluation['task_sha256']:
                    raise ValueError('Frozen task differs from evaluated task')
                result['top_cell'] = task['output']['top_cell']
            if recorded.get('evaluation'):
                checked(archive, recorded['evaluation'])
                original_report = load(archive / 'evaluation/report.json')
                if original_report.get('score') != evaluation.get('score'):
                    raise ValueError('Service score differs from independent evaluator report')
                evaluation_export(archive / 'evaluation', root, files)
        result['harness_stderr'] = traces(runtime, root, files)
        harness = runtime / 'participant/harness-summary.json'
        if harness.exists():
            result['execution'] = load(harness)
        events = runtime / 'participant/observation/service-events.jsonl'
        if events.exists():
            raw = ''.join(json.dumps(without_hashes(json.loads(line))) + '\n'
                          for line in events.read_text().splitlines() if line.strip())
            put(root, 'evaluation/events.jsonl', raw.encode(), files)
        # Archived failures remain attempts, never extra repetitions or alternative scores.
        result['attempts'] = []
        for attempt in sorted((runtime / 'attempts').glob('*')):
            if not attempt.is_dir():
                continue
            entry = {'name': attempt.name}
            if (attempt / 'summary.json').exists():
                entry['summary'] = load(attempt / 'summary.json')
            entry['harness_stderr'] = traces(attempt, root, files, 'attempts/' + attempt.name + '/')
            entry['startup'] = [load(p) for p in sorted(attempt.glob('service/service-store/*/startup.json'))]
            for report in attempt.glob('service/service-store/*/run/run.json'):
                old = load(report)
                if old.get('candidate'):
                    put(root, 'attempts/' + attempt.name + '/final.gds', checked(report.parent, old['candidate']), files)
            result['attempts'].append(entry)
        result = compact_result(result)
        save(root / 'result.json', result)
        from benchmarking.layout_preview import ensure_layout_preview
        ensure_layout_preview(root)
        result = load(root / 'result.json')
        if ((root / 'layout.png').exists() and result.get('image', {}).get('status') == 'complete'
                and 'layout.png' not in result['files']):
            result['files'].append('layout.png')
        text = report_text(result)
        atomic_write(root / 'report.md', text)
        result['files'].append('report.md')
        verify(root, result)
        result['state'] = 'finished'
        save(root / 'result.json', result)
    shutil.rmtree(runtime)
    return result['summary']
