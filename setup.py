"""Embed the source revision so wheel installations need no Git checkout."""
import json
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


def stamp(directory, version):
    source_stamp = Path('benchmarking/_build.json')
    if source_stamp.exists():
        commit = json.loads(source_stamp.read_text())['commit']
    else:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    identity = {'version': version, 'commit': commit}
    (Path(directory) / 'benchmarking/_build.json').write_text(json.dumps(identity) + '\n')


class Build(build_py):
    def run(self):
        super().run()
        stamp(self.build_lib, self.distribution.metadata.version)


class Source(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        stamp(base_dir, self.distribution.metadata.version)


setup(cmdclass={'build_py': Build, 'sdist': Source})
