"""Minimal persisted records from the supported native CLI protocols."""

import json
import sqlite3


def zcode_session(output, session='sess_fixture', *, cwd=None, selection=None):
    """Minimal SQLite records from the supported ZCode 0.16.9 schema."""
    path = output / '.private/native-home/.zcode/cli/db/db.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    cwd = str(cwd or (output / '.private/workspace').resolve())
    selection = selection or {'providerId': 'fixture', 'modelId': 'glm-5.3', 'options': {'reasoningLevel': 'high'}}
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS session (id TEXT PRIMARY KEY, parent_id TEXT, directory TEXT,
                path TEXT, revert TEXT, time_archived INTEGER);
            CREATE TABLE IF NOT EXISTS session_entry (session_id TEXT PRIMARY KEY, type TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS message (id TEXT PRIMARY KEY, session_id TEXT, sequence INTEGER, data TEXT);
            CREATE TABLE IF NOT EXISTS part (message_id TEXT, session_id TEXT, data TEXT, sequence INTEGER DEFAULT 0);
        ''')
        db.execute('INSERT OR REPLACE INTO session VALUES (?, NULL, ?, ?, NULL, NULL)', (session, cwd, cwd))
        db.execute('INSERT OR REPLACE INTO session_entry VALUES (?, ?, ?)',
                   (session, 'runtime/model_selection', json.dumps({'modelSelection': selection})))
        db.execute('INSERT OR REPLACE INTO message VALUES (?, ?, 0, ?)',
                   ('user', session, json.dumps({'role': 'user', 'modelSelection': selection})))
    return path


def native_session(output, harness, session, *, cwd=None, content='retained native reasoning'):
    cwd = str(cwd or (output / '.private/workspace').resolve())
    home = output / '.private/native-home'
    if harness == 'zcode':
        return zcode_session(output, session, cwd=cwd)
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


def codex_tool_reply(session, tool, arguments, result, *, protocol='exec', call_id='call_fixture'):
    """Persist a direct MCP reply or Codex exec's nested MCP and printed output."""
    reply = {'content': [{'type': 'text', 'text': json.dumps(result)}]}
    if protocol == 'exec':
        return [
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec',
                'call_id': call_id, 'input': 'text(await tools.mcp__layout__' + tool + '(args));'}},
            {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': session,
                'item': {'type': 'McpToolCall', 'id': 'exec-' + call_id, 'server': 'layout',
                         'tool': tool, 'arguments': arguments, 'status': 'completed', 'result': reply}}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': call_id,
                'output': [{'type': 'input_text', 'text': 'Script completed\nOutput:\n'},
                           {'type': 'input_text', 'text': json.dumps(reply)}]}},
        ]
    return [
        {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': call_id,
            'name': 'mcp__layout__' + tool, 'arguments': json.dumps(arguments)}},
        {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': call_id,
            'output': json.dumps(reply)}},
    ]
