"""Explicit operator host Spectre X execution with the normal acceptance checks."""

import os
from pathlib import Path

from benchmarking.files import Asset

from ..tools.native import NativeTool
from .spectre_x import SpectreXBackend


class _NativeSpectreTool:
    def __init__(self, runtime, timeout_seconds, *, version_command=('spectre', '-W')):
        self.runtime = runtime
        self.native = NativeTool(runtime, timeout_seconds, failure_label='Spectre')
        probe = self.native.probe(runtime.module_command('spectre', version_command), timeout=timeout_seconds)
        self.version = probe.stdout.decode(errors='replace').strip()
        if probe.returncode or not self.version:
            raise ValueError('Tool did not report a complete release identity')

    @property
    def identity(self):
        return self.native.identity | {'module': 'spectre', 'tool_version': self.version}

    def run(self, command, files, exports):
        return self.native.run(self.runtime.module_command('spectre', command), files, exports)


class SpectreXNative(SpectreXBackend):
    """Trusted evaluator host execution, independently selected from Docker."""

    tool_type = _NativeSpectreTool
    adapter = 'spectre-x-native'

    def _make_tool(self, timeout_seconds):
        return self.tool_type(self.runtime, timeout_seconds)

    @property
    def thread_limit(self):
        return len(os.sched_getaffinity(0))

    @property
    def identity(self):
        return super().identity | {'adapter': 'spectre-x-native',
            'native_adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}
