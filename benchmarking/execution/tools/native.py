"""Explicit evaluator host execution of operator-declared tool installations."""

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from benchmarking.execution._scripts.wait_process_tree import (
    kill_descendants,
    process_snapshot,
)
from benchmarking.execution.tools import ToolResult
from benchmarking.execution.tools.budget import (
    ToolCancelled,
    tool_cancelled,
    tool_timeout,
    wait_for_tool,
)
from benchmarking.files import Asset, relative


class NativeTool:
    """Stage frozen inputs and run one process tree in a fresh host directory."""

    def __init__(self, runtime, timeout_seconds=180, *, failure_label='EDA tool'):
        if timeout_seconds <= 0 or any(m['source'] != m['target'] for m in runtime.mounts):
            raise ValueError('Native tools need positive timeout and identical host/resource paths')
        self.runtime, self.timeout_seconds = runtime, timeout_seconds
        self.failure_label = failure_label
        retained = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR')
        self.environment = {name: os.environ[name] for name in retained if name in os.environ}
        self.environment.update(runtime.environment)
        self.secret_values = []
        for name in runtime.profile.get('pass_environment', []):
            if not os.environ.get(name):
                raise ValueError('Missing external runtime environment setting')
            self.environment[name] = os.environ[name]
            self.secret_values.append(os.environ[name].encode())

    @property
    def identity(self):
        return {'execution': 'operator-native', 'uid': os.getuid(), 'gid': os.getgid(),
                'timeout_seconds': self.timeout_seconds,
                'isolation': 'fresh-job-directory; operator host resources and network',
                'external': self.runtime.identity,
                'native_launcher_sha256': Asset(Path(__file__).read_bytes()
                    + Path(__file__).with_name('budget.py').read_bytes()
                    + Path(__file__).resolve().parents[1].joinpath('_scripts/wait_process_tree.py').read_bytes(),
                    'python').sha256}

    def probe(self, command, *, timeout=60):
        """Run a backend-prepared probe argv in an isolated directory."""
        with tempfile.TemporaryDirectory(prefix='iclayout-native-version-') as temporary:
            return subprocess.run(command, cwd=temporary, env=self.environment, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout, check=False)

    def _evidence(self, content, file_format):
        if file_format == 'text':
            for value in self.secret_values:
                content = content.replace(value, b'<operator-license-setting>')
        return Asset(content, file_format)

    def run(self, command, files, exports, *, evidence_patterns=(), file_rewriter=None,
            failure_label=None):
        if self.runtime.identity != self.runtime._identity:
            raise ValueError('External installation changed since preparation')
        controls = self.runtime.control_assets()
        if controls.keys() & files.keys():
            raise ValueError('Tool inputs collide with native process control files')
        files = controls | files
        for name in (*files, *exports):
            relative(name, 'native tool file')
        evidence, produced, reason, code = {}, {}, '', None
        label = failure_label or self.failure_label
        if tool_cancelled():
            return ToolResult(None, f'Native {label} cancelled', {},
                              {'execution_error': Asset(b'Check cancelled before tool launch', 'text')})
        with tempfile.TemporaryDirectory(prefix='iclayout-native-') as temporary:
            root = Path(temporary)
            for name, asset in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                content = asset.content
                if file_rewriter and name not in controls:
                    content = file_rewriter(name, content, root)
                path.write_bytes(content)
                path.chmod(0o444)
            with (root / 'native-console').open('wb') as log:
                process = subprocess.Popen(command, cwd=root, env=self.environment, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = wait_for_tool(process, tool_timeout(self.timeout_seconds))
                except (subprocess.TimeoutExpired, ToolCancelled) as error:
                    reason = (f'Native {label} cancelled' if isinstance(error, ToolCancelled)
                              else f'Native {label} exceeded its fixed time limit')
                    snapshot = process_snapshot(process.pid)
                    evidence['execution_error'] = self._evidence(json.dumps({
                        'reason': reason, 'processes': snapshot}).encode(), 'text')
                    kill_descendants(snapshot, process.pid)
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            if code not in (None, 0):
                reason = reason or f'Native {label} exited with {code}'
            evidence['console'] = self._evidence((root / 'native-console').read_bytes(), 'text')
            for pattern in evidence_patterns:
                for path in root.glob(pattern):
                    if path.is_file():
                        name = path.relative_to(root).as_posix()
                        evidence[name] = self._evidence(path.read_bytes(), 'text')
            for name, file_format in exports.items():
                path = root / name
                if path.is_file():
                    produced[name] = Asset(path.read_bytes(), file_format)
                else:
                    reason = reason or 'Declared tool output is missing: ' + name
                    evidence['missing:' + name] = Asset(name.encode(), 'text')
        return ToolResult(code, reason, produced, evidence)


class NativeEDATool(NativeTool):
    """Run a declared EDA module on the evaluator host and record its version."""

    def __init__(self, runtime, module, version_command, timeout_seconds=180):
        super().__init__(runtime, timeout_seconds, failure_label=module)
        self.module = module
        result = self.probe(runtime.module_command(module, version_command), timeout=timeout_seconds)
        self.version = self._evidence(result.stdout, 'text').content.decode(errors='replace').strip()
        if result.returncode or not self.version:
            raise ValueError(f'{module} did not report a complete release identity')

    @property
    def identity(self):
        return super().identity | {'module': self.module, 'tool_version': self.version}

    def run(self, command, files, exports, **kwargs):
        return super().run(self.runtime.module_command(self.module, command), files, exports, **kwargs)
