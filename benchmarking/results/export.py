"""Verify and export portable evaluation evidence without participant runtime policy."""

import json
from urllib.parse import quote

from benchmarking.files import atomic_write, checked, read_file

__all__ = ["checked", "compact_report", "compact_result", "evaluation_export", "load", "put", "verify", "without_hashes"]


def load(path):
    return json.loads(path.read_text())



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
    history = {k: result[k] for k in ('attempts', 'prior_plans') if k in result}
    result = without_hashes(result)
    result["identity"] = dict(original_identity)
    result.update(history)
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



def evaluation_export(evidence, root, files, prefix='evaluation'):
    from benchmarking.evaluation.parsing import parse_evaluation
    from benchmarking.evaluation.scoring import recompute_score

    report = evidence.report
    plan_raw = evidence.plan.content
    plan = parse_evaluation(plan_raw, file_format=evidence.plan.format)
    if recompute_score(plan, report) != report.get('score'):
        raise ValueError('Evaluation measurements do not reproduce the stored score')
    put(root, prefix + '/plan.json', plan_raw, files)
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
                raw = evidence.artifact(original)
                # Keep readable logs/measurements inline instead of dozens of tiny files.
                if ref['format'] in {'text', 'json', 'spice', 'tcl', 'magic-ext'}:
                    ref['content'] = raw.decode('utf-8')
                else:
                    sha = ref['sha256']
                    if sha not in retained:
                        filename = quote(job_id + '-' + name, safe='-_.')
                        put(root, prefix + '/' + filename, raw, files)
                        retained[sha] = filename
                    ref['path'] = retained[sha]
    put(root, prefix + '/report.json', (json.dumps(compact_report(report), indent=2) + '\n').encode(), files)
