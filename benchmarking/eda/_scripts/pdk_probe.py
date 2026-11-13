"""Container-local resource smoke checks; not circuit qualification or signoff."""

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

SUPPORT_ROOT = Path("/resources/support")
WORKSPACE = Path("/workspace")


def _resource(support, name):
    path = Path(name)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts):
        raise ValueError("Smoke-check resources must be profile-relative paths")
    resolved = (support / path).resolve(strict=True)
    if (not resolved.is_relative_to(support.resolve(strict=True))
            or any(character in str(resolved) for character in '\"\n\r\x00')):
        raise ValueError("Smoke-check resource escapes the profile")
    return resolved


def spice(profile, model, library, subcircuit, voltage, length, width, section,
          osdi=(), sourcepath=()):
    support = _resource(SUPPORT_ROOT, profile)
    library = _resource(support, library)
    modules = [_resource(support, name) for name in osdi]
    search = [_resource(support, name) for name in sourcepath]
    if not library.is_file() or any(not path.is_file() for path in modules):
        raise ValueError("Smoke-check library and OSDI modules must be files")
    if any(not path.is_dir() for path in search):
        raise ValueError("Smoke-check sourcepath entries must be directories")
    with tempfile.TemporaryDirectory(dir=WORKSPACE, prefix="pdk-smoke-") as temporary:
        root = Path(temporary)
        include = (f'.lib "{library}" {section}' if section
                   else f'.include "{library}"')
        device = "X" if subcircuit else "M"
        # Search paths must be active while parsing .lib/.include, before ordinary
        # control commands run. This startup belongs only to this explicit probe.
        (root / '.spiceinit').write_text(
            'set sourcepath = ( ' + ' '.join(f'"{path}"' for path in search) + ' )\n'
            if search else '')
        # pre_osdi receives its filename literally, unlike .include parsing.
        setup = ''.join(f'pre_osdi {path}\n' for path in modules)
        (root / "probe.spice").write_text(
            f"* Single-device resource loading smoke check\n{include}\n"
            f"Vd d 0 {voltage}\nVg g 0 {voltage}\n"
            f"{device}probe d g 0 0 {model} l={length} w={width}\n"
            f".control\n{setup}op\nlet probe_current=-i(vd)\nprint probe_current\nquit\n.endc\n.end\n")
        environment = os.environ | {"SPICE_USERINIT_DIR": str(root)}
        result = subprocess.run(["ngspice", "-b", "probe.spice"], cwd=root, env=environment,
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
    parser.add_argument("--osdi", action="append", default=[],
                        help="Profile-relative OSDI module to load before parsing (repeatable)")
    parser.add_argument("--sourcepath", action="append", default=[],
                        help="Profile-relative model include directory (repeatable)")
    parser.add_argument("--voltage", default="1")
    parser.add_argument("--length", default="1u")
    parser.add_argument("--width", default="2u")
    spice(**vars(parser.parse_args()))
