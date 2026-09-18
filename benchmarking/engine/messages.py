"""Messages wire protocol validation and usage accounting.

Terminal and cumulative-usage semantics follow the Messages streaming contract:
https://platform.claude.com/docs/en/build-with-claude/streaming
"""

import json


def _content(blocks):
    if isinstance(blocks, str):
        return
    if not isinstance(blocks, list):
        raise TypeError("Message content must be text or local content blocks")
    for block in blocks:
        if not isinstance(block, dict):
            raise TypeError("Invalid content block")
        kind = block.get('type')
        if kind in {'text', 'thinking', 'redacted_thinking', 'tool_use'}:
            continue
        if kind == 'tool_result':
            _content(block.get('content', ''))
        elif kind in {'image', 'document'}:
            source = block.get('source', {})
            if not isinstance(source, dict) or source.get('type') not in {'base64', 'text'}:
                raise ValueError("Only inline image/document sources are allowed")
        else:
            raise ValueError("Remote or unsupported Messages content block")


def _events(body):
    wire = body.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    frames = wire.split('\n\n')
    if frames[-1].strip():
        raise ValueError('Truncated Messages stream')
    for frame in frames[:-1]:
        data, name = [], None
        for line in frame.split('\n'):
            if line.startswith('data:'):
                data.append(line[5:].removeprefix(' '))
            elif line.startswith('event:'):
                name = line[6:].strip()
        if not data:
            continue
        event = json.loads('\n'.join(data))
        if not isinstance(event, dict) or name and event.get('type') != name:
            raise ValueError('Invalid Messages event')
        yield event


class MessagesWireAdapter:
    id = 'messages'

    def validate_request(self, path, body, model):
        if path != '/v1/messages':
            raise ValueError('Only Messages generation is allowed')
        value = json.loads(body)
        allowed = {'model', 'messages', 'max_tokens', 'system', 'tools', 'tool_choice',
                   'temperature', 'top_p', 'top_k', 'stream', 'stop_sequences', 'thinking',
                   'output_config', 'metadata', 'cache_control'}
        if not isinstance(value, dict) or value.get('model') != model or value.keys() - allowed:
            raise ValueError('Messages request differs from the fixed model or allowed fields')
        if type(value.get('max_tokens')) is not int or value['max_tokens'] <= 0:
            raise ValueError('Messages needs positive max_tokens')
        if not isinstance(value.get('messages'), list) or not value['messages']:
            raise ValueError('Messages needs conversation entries')
        for message in value['messages']:
            if not isinstance(message, dict) or message.get('role') not in {'user', 'assistant'}:
                raise ValueError('Invalid Messages role')
            _content(message.get('content'))
        _content(value.get('system', ''))
        tools = value.get('tools', [])
        if not isinstance(tools, list):
            raise TypeError('Invalid Messages tools')
        for tool in tools:
            if (not isinstance(tool, dict) or tool.get('type') not in {None, 'custom'}
                    or not isinstance(tool.get('name'), str) or not isinstance(tool.get('input_schema'), dict)):
                raise ValueError('Only client-executed custom tools are allowed')
        return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()

    def prepare_request(self, path, body, model, credential):
        from .inference import WireRequest

        return WireRequest('POST', path, {'x-api-key': credential,
                                         'anthropic-version': '2023-06-01',
                                         'Content-Type': 'application/json',
                                         'Accept': 'application/json, text/event-stream'})

    def response_semantics(self, path, content_type, body):
        from .inference import normalize_usage

        media = content_type.split(';', 1)[0].strip().lower()
        if media == 'application/json':
            response = json.loads(body)
            if not isinstance(response, dict):
                raise ValueError('Invalid Messages response')
        elif media == 'text/event-stream':
            response, stopped = None, False
            for event in _events(body):
                kind = event.get('type')
                if kind == 'ping':
                    continue
                if stopped:
                    raise ValueError('Events after Messages terminal state')
                if kind == 'error':
                    response, stopped = event, True
                elif kind == 'message_start':
                    if response is not None or not isinstance(event.get('message'), dict):
                        raise ValueError('Duplicate or invalid message_start')
                    response = dict(event['message'])
                elif kind == 'message_delta':
                    if response is None or not isinstance(event.get('delta'), dict):
                        raise ValueError('Message delta without a start')
                    response.update(event['delta'])
                    if 'usage' in event:
                        response['usage'] = {**(response.get('usage') or {}), **event['usage']}
                elif kind == 'message_stop':
                    if response is None:
                        raise ValueError('Message stop without a start')
                    stopped = True
            if not stopped:
                raise ValueError('Missing message_stop')
        else:
            raise ValueError('Unsupported Messages media type')
        if response.get('type') == 'error':
            return {'outcome': 'service_error', 'reason': (response.get('error') or {}).get('type'), 'usage': None}
        if response.get('type') != 'message':
            raise ValueError('Missing Messages response object')
        reason = response.get('stop_reason')
        if reason in {'end_turn', 'stop_sequence', 'tool_use'}:
            outcome = 'completed'
        elif reason in {'max_tokens', 'model_context_window_exceeded'}:
            outcome = 'budget_truncated'
        elif reason == 'refusal':
            outcome = 'content_filtered'
        elif reason:
            outcome = 'incomplete_error'
        else:
            raise ValueError('Missing Messages stop reason')
        raw = response.get('usage')
        if raw is not None:
            if not isinstance(raw, dict):
                raise ValueError('Invalid Messages usage')
            usage = {key: raw.get(key) for key in ('input_tokens', 'output_tokens')}
            for key in ('cache_creation_input_tokens', 'cache_read_input_tokens'):
                value = raw.get(key)
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError('Invalid Messages cache usage')
                if value is not None and type(usage['input_tokens']) is int:
                    usage['input_tokens'] += value
            usage['cached_input_tokens'] = raw.get('cache_read_input_tokens')
            usage = normalize_usage(usage)
        else:
            usage = None
        return {'outcome': outcome, 'reason': reason, 'usage': usage}
