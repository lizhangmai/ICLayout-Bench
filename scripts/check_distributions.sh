#!/usr/bin/env bash
# Install every built wheel and sdist into a fresh virtual environment, then
# check the installed entry points and the embedded release identity.
# Usage: scripts/check_distributions.sh DIST_DIR EXPECTED_COMMIT
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 DIST_DIR EXPECTED_COMMIT" >&2
    exit 2
fi
dist="$(cd "$1" && pwd)"
expected_commit="$2"
python="${PYTHON:-python3}"
work="$(mktemp -d "${TMPDIR:-/tmp}/iclayout-bench-dist.XXXXXX")"
trap 'rm -rf "${work}"' EXIT

shopt -s nullglob
wheels=("${dist}"/*.whl)
sdists=("${dist}"/*.tar.gz)
if [ "${#wheels[@]}" -eq 0 ] || [ "${#sdists[@]}" -eq 0 ]; then
    echo "Expected at least one wheel and one sdist in ${dist}" >&2
    exit 1
fi

for artifact in "${wheels[@]}" "${sdists[@]}"; do
    echo "Checking $(basename "${artifact}")"
    venv="${work}/venv-$(basename "${artifact}")"
    "${python}" -m venv "${venv}"
    "${venv}/bin/python" -m pip install --quiet --disable-pip-version-check "iclayout-bench[results] @ file://${artifact}"
    (cd "${work}" && EXPECTED_COMMIT="${expected_commit}" "${venv}/bin/python" -I - <<'PYCODE'
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import benchmarking
from benchmarking.version import package_version

assert Path(benchmarking.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
identity = package_version()
assert identity["version"] == version("iclayout-bench"), identity
assert identity["commit"] == os.environ["EXPECTED_COMMIT"], identity
for name in ("benchmarking.run", "benchmarking.service", "benchmarking.evaluation",
             "benchmarking.execution", "benchmarking.eda"):
    subprocess.run([sys.executable, "-I", "-m", name, "--help"], check=True,
                   stdout=subprocess.DEVNULL)
PYCODE
    )
done
