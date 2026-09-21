"""Public release identity, shared by source runs and built distributions."""
import json
import subprocess
from importlib.metadata import version
from pathlib import Path


def package_version():
    root = Path(__file__).resolve().parent
    stamp = root / '_build.json'
    if stamp.exists():
        return json.loads(stamp.read_text())
    project = root.parent
    commit = None
    if (project / '.git').exists():
        commit = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    return {'version': version('iclayout-bench'), 'commit': commit}
