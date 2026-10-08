"""Explicit evaluator host execution of operator-declared tool installations."""

import os
import signal
import subprocess
import tempfile
from pathlib import Path

from benchmarking.files import Asset, relative

from .budget import tool_timeout
from .types import ToolResult


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
                'native_launcher_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}

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
        for name in (*files, *exports):
            relative(name, 'native tool file')
        evidence, produced, reason, code = {}, {}, '', None
        label = failure_label or self.failure_label
        with tempfile.TemporaryDirectory(prefix='iclayout-native-') as temporary:
            root = Path(temporary)
            for name, asset in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                content = asset.content
                if file_rewriter:
                    content = file_rewriter(name, content, root)
                path.write_bytes(content)
                path.chmod(0o444)
            with (root / 'native-console').open('wb') as log:
                process = subprocess.Popen(command, cwd=root, env=self.environment, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=tool_timeout(self.timeout_seconds))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    reason = f'Native {label} exceeded its fixed time limit'
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
