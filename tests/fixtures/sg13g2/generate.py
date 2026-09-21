"""Generate the public extraction fixtures with a verified primitive view."""

import argparse
import json
import os
from pathlib import Path

from benchmarking.bundles import load_bundle
from benchmarking.engine.docker import DockerTool
from benchmarking.files import Asset

EXAMPLES = Path(__file__).resolve().parent


def generate_fixtures(view: Path, destination: Path) -> dict[str, Asset]:
    view_digest = load_bundle(view).manifest.sha256
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    tool = DockerTool(os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local"), ["magic", "--version"], 60)
    primitive_files = {"pdk/" + name: asset for name, asset in load_bundle(view).files}
    environment = {"KLAYOUT": "1", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONPATH": "/workspace/pdk/ihp-sg13g2/libs.tech/klayout/python:"
                                 "/workspace/pdk/ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api/source/python"}
    outputs, records = {}, []
    destination.mkdir(parents=True)
    cases = (
        ("plate20", "make_plate.py", ["--width", "20", "--height", "10"]),
        ("plate40", "make_plate.py", ["--width", "40", "--height", "10"]),
        ("switch10", "make_switch.py", ["--plate", "10"]),
        ("switch100", "make_switch.py", ["--plate", "100"]),
    )
    for name, script, args in cases:
        source = Asset((EXAMPLES / script).read_bytes(), "python")
        files = {script: source, **(primitive_files if script != "make_plate.py" else {})}
        command = ["python", script, "fixture.gds", *args]
        result = tool.run(command, files, {"fixture.gds": "gds"}, environment=environment)
        (destination / f"{name}.log").write_bytes(result.evidence["console"].content)
        if result.reason:
            raise ValueError(f"Fixture generation failed: {result.reason}; see {destination}")
        outputs[name] = result.files["fixture.gds"]
        (destination / f"{name}.gds").write_bytes(outputs[name].content)
        records.append({"name": name, "command": command, "source_sha256": source.sha256,
                        "output": outputs[name].identity()})
    (destination / "generation.json").write_text(json.dumps(
        {"tool": tool.identity, "primitive_view_sha256": view_digest, "fixtures": records}, indent=2) + "\n")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("view", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    generate_fixtures(args.view, args.destination)
