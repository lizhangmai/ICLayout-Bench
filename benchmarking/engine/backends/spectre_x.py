"""Spectre X execution with the standard Spectre inputs and result checks."""

from pathlib import Path

from benchmarking.files import Asset

from ..tools.docker import DockerTool
from .spectre import SpectreBackend, SpectreDocker


class _SpectreXTool:
    def __init__(self, tool, threads, preset, postlayout_preset=None, preset_override=()):
        self.tool, self.threads, self.preset = tool, threads, preset
        self.postlayout_preset = postlayout_preset
        self.preset_override = preset_override

    @property
    def identity(self):
        return self.tool.identity

    def run(self, command, files, exports, **kwargs):
        if command[:1] != ['spectre']:
            raise ValueError('Spectre X execution requires a Spectre command')
        options = ([f'+postlpreset={self.postlayout_preset}'] if self.postlayout_preset else [])
        if self.preset_override:
            options.append('-preset_override='+','.join(self.preset_override))
        return self.tool.run([command[0], f'+preset={self.preset}',
                              f'+mt={self.threads}', *options, *command[1:]],
                             files, exports, **kwargs)


class SpectreXBackend(SpectreBackend):
    """Shared Spectre X controls for independently selected transports."""

    @property
    def thread_limit(self):
        raise NotImplementedError("A Spectre X transport must declare its CPU allocation")

    def __init__(self, *, threads=4, preset='ax', postlayout_preset=None, preset_override=(), **settings):
        if type(threads) is not int or not 1 <= threads <= self.thread_limit:
            raise ValueError('Spectre X threads must fit the tool CPU allocation')
        if preset not in ('cx', 'ax', 'mx', 'lx', 'vx'):
            raise ValueError('Spectre X preset must be cx, ax, mx, lx or vx')
        if postlayout_preset not in (None, 'cx', 'ax', 'mx', 'lx', 'vx'):
            raise ValueError('Invalid Spectre X postlayout preset')
        if not isinstance(preset_override, (list, tuple)) or not set(preset_override) <= {
                'maxstep', 'reltol', 'vabstol', 'iabstol'}:
            raise ValueError('Invalid Spectre X overridden parameters')
        super().__init__(**settings)
        self.threads, self.preset = threads, preset
        self.postlayout_preset = postlayout_preset
        self.preset_override = list(preset_override)
        self.tool = _SpectreXTool(self.tool, threads, preset, postlayout_preset, preset_override)

    @property
    def identity(self):
        return {**super().identity, 'adapter': self.adapter,
                'threads': self.threads, 'preset': self.preset,
                'postlayout_preset': self.postlayout_preset,
                'preset_override': self.preset_override,
                'x_adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}


class SpectreXDocker(SpectreXBackend, SpectreDocker):
    """Run licensed Spectre X in the bounded evaluator container."""

    adapter = 'spectre-x-docker'

    @property
    def thread_limit(self):
        return DockerTool.CPUS
