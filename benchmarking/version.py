"""Public release identity, shared by source runs and built distributions."""
import json
import subprocess
import tomllib
from pathlib import Path


def package_version():
    root = Path(__file__).resolve().parent
    stamp = root / '_build.json'
    if stamp.exists():
        return json.loads(stamp.read_text())
    project = root.parent
    version = tomllib.loads((project / 'pyproject.toml').read_text())['project']['version']
    commit = None
    if (project / '.git').exists():
        commit = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    return {'version': version, 'commit': commit}
