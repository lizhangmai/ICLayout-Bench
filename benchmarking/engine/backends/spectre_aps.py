"""Explicit APS execution, sharing Spectre inputs and acceptance semantics."""

from pathlib import Path

from benchmarking.files import Asset

from ..tools.docker import DockerTool
from .spectre import SpectreDocker


class _APSTool:
    def __init__(self, tool, threads, aps_preset, postlayout):
        self.tool, self.threads = tool, threads
        self.aps_preset, self.postlayout = aps_preset, postlayout

    @property
    def identity(self):
        return self.tool.identity

    def run(self, command, files, exports, **kwargs):
        if command[:1] != ['spectre']:
            raise ValueError('APS execution requires a Spectre command')
        options = [f'++aps={self.aps_preset}' if self.aps_preset else '+aps',
                   f'+mt={self.threads}']
        if self.postlayout:
            options.append('+postlayout' if self.postlayout == 'default'
                           else f'+postlayout={self.postlayout}')
        return self.tool.run([command[0], *options, *command[1:]],
                             files, exports, **kwargs)


class SpectreAPSDocker(SpectreDocker):
    """Opt into licensed APS without changing the classic Spectre adapter."""

    adapter = 'spectre-aps-docker'

    def __init__(self, *, threads=4, aps_preset=None, postlayout=None, **settings):
        if type(threads) is not int or not 1 <= threads <= DockerTool.CPUS:
            raise ValueError('APS threads must fit the tool CPU allocation')
        if aps_preset not in (None, 'conservative', 'moderate', 'liberal'):
            raise ValueError('APS preset must be conservative, moderate or liberal')
        if postlayout not in (None, 'upa', 'hpa', 'default'):
            raise ValueError('APS postlayout must be upa, hpa or default')
        super().__init__(**settings)
        self.threads, self.aps_preset, self.postlayout = threads, aps_preset, postlayout
        self.tool = _APSTool(self.tool, threads, aps_preset, postlayout)

    @property
    def identity(self):
        return {**super().identity, 'adapter': 'spectre-aps-docker', 'threads': self.threads,
                'aps_preset': self.aps_preset, 'postlayout': self.postlayout,
                'aps_adapter_sha256': Asset(Path(__file__).read_bytes(), 'python').sha256}
