"""Minimal persisted records from the supported native CLI protocols."""

import json


def native_session(output, harness, session, *, cwd=None, content='retained native reasoning'):
    cwd = str(cwd or (output / '.private/workspace').resolve())
    home = output / '.private/native-home'
    if harness == 'codex':
        path = home / 'sessions/2026/10/09' / ('rollout-fixture-' + session + '.jsonl')
        events = [{'type': 'session_meta', 'payload': {'id': session, 'cwd': cwd}},
                  {'type': 'response_item', 'payload': {'type': 'reasoning', 'text': content}}]
    elif harness == 'claude-code':
        path = home / 'projects/workspace' / (session + '.jsonl')
        events = [{'type': 'user', 'sessionId': session, 'cwd': cwd, 'isSidechain': False},
                  {'type': 'assistant', 'sessionId': session, 'cwd': cwd, 'isSidechain': False,
                   'message': {'content': [{'type': 'thinking', 'thinking': content}]}}]
    else:
        raise ValueError(harness)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event) + '\n' for event in events))
    return path
