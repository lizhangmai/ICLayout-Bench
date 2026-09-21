"""Bind an already materialized test case to its local input snapshots."""

import math
import re
import tomllib

import tomli_w


def standalone_config(config):
    data = tomllib.loads(config)
    for entry in data["task"]["inputs"].values():
        entry.pop("source", None)
    return tomli_w.dumps(data)


def calibration_limits(case):
    """Read maintainer tolerances from the case README's calibration table.

    These values qualify a model-boundary approximation; they are not task
    acceptance limits and must not be distributed as solver inputs.
    """
    text = (case / "README.md").read_text()
    section = text.split("### Calibration limits\n", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \|$", section, re.MULTILINE)
    assert rows, f"Missing calibration limits: {case}"
    limits = {}
    for name, unit, value in rows:
        assert name not in limits and unit.strip(), (case, name)
        limits[name] = float(value)
        assert math.isfinite(limits[name]) and limits[name] > 0, (case, name)
    return limits
