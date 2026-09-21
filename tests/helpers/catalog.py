"""Read published case metadata without walking upstream assets."""

import os
import tomllib
from pathlib import Path

ROOT = Path(os.environ.get("ICLAYOUT_BENCH_DATASET", "build/no-dataset")).resolve()
CASES = sorted((ROOT / "tasks").glob("*/*/cases/*/case.toml"))


def read_case(path):
    return tomllib.loads(path.read_text())
