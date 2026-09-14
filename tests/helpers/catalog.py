"""Read declared public catalog metadata without walking upstream assets."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = sorted((ROOT / "tasks").glob("*/*/catalog.toml"))


def read_catalog(path):
    catalog = tomllib.loads(path.read_text())
    configs = [(path.parent / item["config_path"],
                tomllib.loads((path.parent / item["config_path"]).read_text()))
               for item in catalog["cases"]]
    return catalog, configs
