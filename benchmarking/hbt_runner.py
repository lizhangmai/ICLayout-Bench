"""Run the reviewed SG13G2 KLayout extraction runset in a container.

The normal KLayout adapter runs a comparison against an authoritative source
netlist.  HBT post-layout extraction has a different contract: it needs the
layout netlist even when the source circuit is intentionally independent of an
upstream schematic.  This runner therefore fixes ``net_only=true`` and never
accepts a source netlist from the caller.

Only the runset and its reviewed support bundle are mounted into the
container.  The host adapter validates and converts the resulting native
KLayout netlist; this file deliberately does not make any simulator claims.
"""

import json
import subprocess
from pathlib import Path


def _run(config: dict) -> tuple[str, str, dict]:
    """Execute the pinned deck and return a serialisable status tuple."""
    wrapper = Path("extract.lvs")
    wrapper.write_text(
        f'# %include /workspace/support/{config["deck"]}\n'
        + 'File.write("/workspace/complete.txt", "complete\\n")\n'
    )
    variables = {
        **config["variables"],
        "input": "/workspace/candidate.gds",
        "topcell": config["top_cell"],
        "report": "/workspace/report.db",
        "log": "/workspace/deck.log",
        "net_only": "true",
        "target_netlist": "/workspace/extracted.spice",
    }
    command = ["klayout", "-b", "-r", str(wrapper)]
    command.extend(arg for name, value in variables.items() for arg in ("-rd", f"{name}={value}"))
    with Path("tool.log").open("wb") as log:
        run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    complete = Path("complete.txt")
    extracted = Path("extracted.spice")
    if run.returncode:
        return "error", f"KLayout exited with {run.returncode}", {"returncode": run.returncode}
    if not complete.is_file() or complete.read_text() != "complete\n":
        return "error", "KLayout extraction did not reach its completion marker", {}
    if not extracted.is_file() or not extracted.read_bytes().strip():
        return "error", "KLayout did not produce a nonempty extracted netlist", {}
    return "passed", "", {"top_cell": config["top_cell"], "variables": variables}


def main() -> None:
    config = json.loads(Path("config.json").read_text())
    for name in ("tool.log", "complete.txt", "extracted.spice", "result.json"):
        Path(name).touch()
    try:
        status, reason, details = _run(config)
    except Exception as error:  # noqa: BLE001 -- preserve an adapter error as evidence
        status, reason, details = "error", f"{type(error).__name__}: {error}", {}
    Path("result.json").write_text(json.dumps({"status": status, "reason": reason,
                                                "details": details}, indent=2))


if __name__ == "__main__":
    main()
