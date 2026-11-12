"""Explicit replacement of unfinished cases, preserving their original evidence."""

import copy
import json
from pathlib import Path
from uuid import uuid4

from benchmarking.client import Client
from benchmarking.execution.leases import BatchLease
from benchmarking.files import sync_directory
from benchmarking.files import write_json as save
from benchmarking.participants.attempt.state import ParticipantAttempt
from benchmarking.participants.attempt.storage import CaseRecord


def content_identity(identity):
    """Match local Datasets by recorded digests; their Git commit is provenance only.

    Repository-ID sources keep their snapshot commit, which addresses content.
    """
    result = copy.deepcopy(identity)
    plan = result.get('plan') if isinstance(result.get('plan'), list) else []
    inputs = result.get('inputs') if isinstance(result.get('inputs'), dict) else {}
    for entry in [row.get('dataset') for row in plan if isinstance(row, dict)] + [
            item.get('dataset') for item in inputs.values() if isinstance(item, dict)]:
        if isinstance(entry, dict) and isinstance(entry.get('source'), str) and Path(entry['source']).is_absolute():
            entry.pop('commit', None)
    return result


def comparable(identity):
    """A repair may change runner/CLI/recovery versions, never solve conditions."""
    identity = content_identity(identity)
    result = {k: v for k, v in identity.items() if k not in {'benchmark', 'cli_version', 'plan'}}
    result['plan'] = [{k: v for k, v in row.items() if k not in {'recovery', 'name'}}
                      for row in identity['plan']]
    return result


def same_solve_conditions(recorded, current):
    """Records from releases without PDK file digests compare on the content they recorded."""
    recorded, current = comparable(recorded), comparable(current)
    inputs = current.get('inputs') if isinstance(current.get('inputs'), dict) else {}
    for task, entry in (recorded.get('inputs') if isinstance(recorded.get('inputs'), dict) else {}).items():
        if isinstance(entry, dict) and 'pdk_files_sha256' not in entry and isinstance(inputs.get(task), dict):
            inputs[task].pop('pdk_files_sha256', None)
    return recorded == current


def validate_replacement(root, identity):
    journal = root / '.replacement.json'
    transaction = json.loads(journal.read_text()) if journal.exists() else None
    record = transaction['previous'] if transaction else CaseRecord(root).read()
    if transaction and content_identity(transaction['identity']) != content_identity(identity):
        raise ValueError('Interrupted replacement requires its recorded target conditions: ' + str(root))
    if record['state'] not in {'pending', 'blocked', 'suspended'}:
        raise ValueError('Replacement requires a pending, blocked or suspended case; collect other states first: ' + str(root))
    if not same_solve_conditions(record['identity'], identity):
        raise ValueError('Replacement cannot change model, effort, inputs, image, endpoint or repetitions: ' + str(root))
    terminal = root / '.runtime/summary.json'
    if not transaction and terminal.exists() and json.loads(terminal.read_text()).get('state') == 'finished':
        raise ValueError('A terminal export must be collected, not replaced: ' + str(root))
    participant = CaseRecord(root).participant
    endpoint = record['identity'].get('endpoint')
    if not transaction and endpoint and ParticipantAttempt.exists(participant):
        state = ParticipantAttempt.read_state(participant)
        if state.created is None:
            raise ValueError('Uncertain session creation must be reconciled before replacement')
        created = state.created
        session = Client(endpoint, created['session_token'], timeout=60).session(created['session_id'])
        if session['state'] not in {'complete', 'error'}:
            raise ValueError('Collect the existing remote session before replacement')
    return transaction or {'previous': record, 'identity': identity, 'name': uuid4().hex,
                           'kind': 'plans' if record['state'] == 'pending' else 'attempts'}


def lease_replacement(root, stack):
    """Reject live local services before any selected case is changed."""
    for base in (root / '.runtime', root / '.replacing'):
        for store in sorted(base.rglob('service-store')):
            stack.enter_context(BatchLease(store))


def replace_unfinished(root, transaction):
    """Caller holds case/store leases. The journal makes interrupted moves repeatable."""
    runtime, staging = root / '.runtime', root / '.replacing'
    destination = runtime / transaction['kind'] / transaction['name']
    journal = root / '.replacement.json'
    save(journal, transaction)
    if not destination.exists():
        if runtime.exists() and not staging.exists():
            runtime.rename(staging)
        runtime.mkdir(mode=0o700, exist_ok=True)
        # Keep previous replacement histories flat across repeated explicit repairs.
        for group in ('attempts', 'plans'):
            previous = staging / group
            if previous.exists():
                target = runtime / group
                target.mkdir(mode=0o700, exist_ok=True)
                for entry in previous.iterdir():
                    entry.rename(target / entry.name)
                sync_directory(target)
                previous.rmdir()
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        if staging.exists():
            staging.rename(destination)
        else:
            destination.mkdir(mode=0o700)
        sync_directory(destination.parent)
        sync_directory(runtime)
        sync_directory(root)
    save(destination / 'record.json', transaction['previous'])
    CaseRecord(root).initialize(transaction['identity'])
    journal.unlink()
