"""Embed the source revision so wheel installations need no Git checkout."""
import json
import runpy
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


def stamp(directory):
    identity = runpy.run_path('benchmarking/version.py')['package_version']()
    (Path(directory) / 'benchmarking/_build.json').write_text(json.dumps(identity) + '\n')


class Build(build_py):
    def run(self):
        super().run()
        stamp(self.build_lib)


class Source(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        stamp(base_dir)


setup(cmdclass={'build_py': Build, 'sdist': Source})
