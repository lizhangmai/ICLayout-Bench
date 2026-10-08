"""Pure HTTP projections of durable runs, workspace state and judge reports."""

from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY
from benchmarking.protocol import USAGE_FIELDS


def status(data, workspace, events, now):
    if data.get('interrupted'):
        state = 'error'
    elif 'report' in data:
        state = 'error' if data['report']['outcome'] == 'error' else 'complete'
    elif data.get('closing') or workspace is not None and not workspace.active:
        state = 'evaluating'
    else:
        state = 'active'
    subs = data['submissions']
    checks = completed = 0
    evaluation_seconds = 0.0
    for event in events:
        checks += event.get('kind') == 'process_feedback.request'
        if event.get('kind') == 'process_feedback.result':
            completed += 1
            evaluation_seconds += event.get('data', {}).get('elapsed_seconds', 0.0)
    remaining = max(0, data['deadline_epoch'] - now)
    budget = {'policy': data['limits'].get('budget_policy', 'hard'),
              'remaining_seconds': remaining,
              'overrun_seconds': max(0, now - data['deadline_epoch']) if state == 'active' else
                  max(0, data.get('report', {}).get('elapsed_seconds', 0) - data['limits']['wall_seconds']),
              'message': 'Solve budget exhausted. Finish the operation already in progress and submit immediately; do not start another optimization round.' if remaining == 0 else
                  f'{remaining:.1f} seconds remain in the solve budget.'}
    return {'session_id': data['session_id'], 'state': state, 'created_at': data['created_at'], 'budget': budget,
                'deadline': data['deadline'], 'remaining_seconds': max(0, data['deadline_epoch']-now)
                if state == 'active' else 0,
                'active_execution_id': next((k for k, v in data['executions'].items() if v['state']=='running'), None),
                'last_submission': max(subs.values(), key=lambda s:s['sequence']) if subs else None,
                'capabilities': [PROCESS_FEEDBACK_CAPABILITY],
                'diagnostics': {'requests': checks, 'completed': completed, 'elapsed_seconds': evaluation_seconds},
                'opinions_remaining': 0}



def result(data, status, judged=None):
    report = data.get('report', {})
    verdict = {'passed':'pass', 'failed':'fail', 'no_submission':'no_submission', 'error':'error'}.get(report.get('outcome'))
    if data.get('interrupted'):
        verdict = 'error'
    metrics = {}
    failure_reason = report.get('evaluation_error')
    if judged is not None:
        metrics = judged.get('metrics', {})
        rejected = [name + ': ' + job['status']
                    for name, job in judged.get('jobs', {}).items() if job['status'] != 'passed']
        if verdict in ('fail', 'error'):
            failure_reason = '; '.join(rejected) or 'Task requirements not satisfied'
    elif verdict in ('no_submission', 'error'):
        failure_reason = failure_reason or report.get('reason') or report.get('termination')
    return {'session_id': data['session_id'], 'state': status['state'], 'task_id': data['task_id'],
                'task_sha256': data['task_sha256'], 'condition': data['condition'], 'tool_identity': data['tool_identity'],
                'limits': data['limits'], 'evaluation_mode': 'self_run',
                'provenance': {'candidate': 'server_observed' if status['last_submission'] else 'unknown',
                                'interaction': 'server_observed', 'condition': 'participant_reported', 'usage': 'unknown'},
                'usage': dict.fromkeys(USAGE_FIELDS), 'diagnostics': status['diagnostics'], 'submission': status['last_submission'], 'outcome': verdict,
                'task_success': report.get('task_success'), 'score': report.get('score'), 'metrics': metrics,
                'failure_category': ('service_failure' if data.get('interrupted') or report.get('termination') == 'infrastructure_error'
                                     else 'evaluation_tool_error' if verdict == 'error' and report.get('evaluation_error')
                                     else 'unknown' if verdict == 'error' else None),
                'failure_reason': data.get('startup_failure', 'service_interrupted') if data.get('interrupted') else failure_reason, 'evidence': []}
