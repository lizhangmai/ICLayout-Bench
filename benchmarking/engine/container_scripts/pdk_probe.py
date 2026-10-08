"""Container-local resource smoke checks; not circuit qualification or signoff."""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def spice(profile, model, library, subcircuit, voltage, length, width, section):
    support = Path("/resources/support") / profile
    with tempfile.TemporaryDirectory(dir="/workspace", prefix="pdk-smoke-") as temporary:
        root = Path(temporary)
        startup = support / ".spiceinit"
        if startup.exists():
            (root / ".spiceinit").write_bytes(startup.read_bytes())
        include = (f'.lib "{support / library}" {section}' if section
                   else f'.include "{support / library}"')
        device = "X" if subcircuit else "M"
        (root / "probe.spice").write_text(
            f"* Single-device resource loading smoke check\n{include}\n"
            f"Vd d 0 {voltage}\nVg g 0 {voltage}\n"
            f"{device}probe d g 0 0 {model} l={length} w={width}\n"
            ".control\nop\nlet probe_current=-i(vd)\nprint probe_current\nquit\n.endc\n.end\n")
        result = subprocess.run(["ngspice", "-b", "probe.spice"], cwd=root,
                                capture_output=True, text=True, timeout=60, check=False)
        print(result.stdout, result.stderr, flush=True)
        current = re.search(r"probe_current\s*=\s*([+\-0-9.eE]+)", result.stdout)
        assert result.returncode == 0 and current and float(current[1]) > 0, "Model operating point failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile")
    parser.add_argument("model")
    parser.add_argument("library")
    parser.add_argument("--subcircuit", action="store_true")
    parser.add_argument("--section")
    parser.add_argument("--voltage", default="1")
    parser.add_argument("--length", default="1u")
    parser.add_argument("--width", default="2u")
    spice(**vars(parser.parse_args()))
