"""Check invocation-scoped DSH overlays without making model calls."""
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from benchmarking.participants.dsh import prepare

pytestmark = pytest.mark.unit


class DshPatchTests(unittest.TestCase):
    def test_default_effort_is_omitted_and_host_tools_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {'rows': [{'id': 'tool-bash'}, {'id': 'tool-fs'}, {'id': 'tool-subagent'},
                                 {'id': 'agent-instructions'}, {'id': 'mcp-other'}, {'id': 'llm-deepseek'}],
                        'mcp_servers': {'a': {'command': '/tools/a', 'args': ['serve'], 'env': {'A_API_KEY': 'private-a'}}},
                        'settings': {'llm-pi-ai': {'providers': {}}, 'unrelated': {'flag': True}}}
            original = json.dumps(settings, sort_keys=True)
            env = {'ICLAYOUT_BENCH_TOKEN': 'scoped-fixture', 'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '600',
                   'DEEPSEEK_API_KEY': 'provider-fixture'}
            condition = {'provider': 'deepseek-official', 'model': 'deepseek-flash', 'effort_resolved': None}
            args = prepare(condition, settings, env, root, root / 'output', root / 'bridge.py', 'task')
            self.assertEqual(args[:3], ['dsh', '--profile', 'headless'])
            self.assertNotIn('provider-fixture', json.dumps(args))
            self.assertNotIn('private-a', json.dumps(args))
            config = json.loads((root / 'dsh-settings.json').read_text())
            self.assertNotIn('reasoningEffort', config['agent-default-model'])
            self.assertNotIn('unrelated', config)
            overlay = json.loads((root / 'dsh.patch.json').read_text())
            disabled = {r['id'] for r in overlay if r.get('disabled')}
            self.assertTrue({'tool-bash', 'tool-fs', 'tool-subagent', 'agent-instructions', 'mcp-other'} <= disabled)
            added = {r['insert'][0]['config']['serverName']: r['insert'][0]['config'] for r in overlay if 'insert' in r}
            self.assertEqual(added['a']['command'], '/tools/a')
            self.assertEqual(added['a']['env'], {'A_API_KEY': 'private-a'})
            mcp = next(r['insert'][0] for r in overlay if 'insert' in r)
            self.assertEqual(mcp['config']['env']['ICLAYOUT_BENCH_TOKEN'], 'scoped-fixture')
            self.assertNotIn('DEEPSEEK_API_KEY', mcp['config']['env'])
            self.assertEqual((root / 'dsh-settings.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.dumps(settings, sort_keys=True), original)
            condition['effort_resolved'] = 'max'
            prepare(condition, settings, env, root, root / 'output', root / 'bridge.py', 'task')
            config = json.loads((root / 'dsh-settings.json').read_text())
            self.assertEqual(config['agent-default-model']['reasoningEffort'], 'max')


if __name__ == '__main__':
    unittest.main()
