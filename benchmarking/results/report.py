"""Readable reports derived from portable terminal participant records."""


from benchmarking.protocol import evaluation_mode


def report_text(result):
    evaluation = result.get('evaluation') or {}
    summary = result['summary']
    score = evaluation.get('score') or {}
    row = result['identity']['plan'][0]
    lines = [f"# {summary.get('task', evaluation.get('task_id', 'Case'))}", '',
             f"Model: `{row.get('model')}`; effort: `{row.get('effort')}`; outcome: **{summary.get('outcome')}**.",
             f"Score: **{summary.get('score')}** (maximum = {score.get('maximum')}); evaluation mode: `{evaluation_mode(evaluation)}`.",
             f"Agent time: {result.get('execution', {}).get('elapsed_seconds', 'unknown')} seconds (excludes preparation and evaluation).", '',
             '[Machine-readable result](result.json)', '']
    benchmark = result['identity'].get('benchmark') or {}
    lines += [f"ICLayout-Bench: `{benchmark.get('version') or 'unknown'}`; Git commit: `{benchmark.get('commit') or 'unknown'}`.", '']
    if 'final.gds' in result.get('files', []):
        lines += ['[Submitted GDS](final.gds) · [Layout image](layout.png)', '']
    if score.get('method') == 'layout':
        formula = '`S = 100 × G × product(min(1, q_i) ** w_i)` with explicit metric and area weights.'
        lines += ['## Scoring', '', formula, '',
                  'Each metric uses its worst paired target-relative quality, capped at 1 before weighting. E and Q contain credited qualities. Scores range from 0 to 100. Errors are unknown; functional rejection is zero.', '',
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
        lines += ['', '## Source comparisons', '', '| Metric | Source observations | Raw quality | Credited quality |',
                  '| --- | --- | ---: | ---: |']
        for key, metric in evaluation.get('metrics', {}).items():
            baseline = metric.get('baseline', [])
            if not baseline:
                continue
            observations = []
            for ref in baseline:
                job, name = ref.split(':')
                value = evaluation.get('jobs', {}).get(job, {}).get('measurements', {}).get(name, {}).get('value')
                observations.append(f'{ref} = {value}')
            lines.append(f"| {key} | {'; '.join(observations)} | {score.get('metrics', {}).get(key)} | {score.get('credited_metrics', {}).get(key)} |")
    lines += ['', 'Full individual observations are retained in result.json. Local results cover only the declared case conditions; they are not manufacturing signoff or repeated-run reliability evidence.', '',
              'Reusable PDK/tool sources and native credentials are not retained. Inputs are defined by the recorded ICLayout-Bench release.', '']
    return '\n'.join(lines).encode()
