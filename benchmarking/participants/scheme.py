"""Resolve declared participant tools and commands without importing user code."""

import hashlib
import os
import re
import shutil
from pathlib import Path

from benchmarking.files import read_file


def launch_spec(value, base):
    """Freeze an argv executable and explicitly declared local files."""
    if not isinstance(value, dict) or set(value) - {"command", "files", "env_vars"}:
        raise ValueError("Launch needs command, files and optional env_vars")
    argv = value.get("command")
    files = value.get("files")
    variables = value.get("env_vars", [])
    if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v for v in argv):
        raise ValueError("command must be a nonempty argv list")
    if not isinstance(files, list) or any(not isinstance(v, str) for v in files):
        raise ValueError("Declare launch files, including scripts and dependency locks")
    if (not isinstance(variables, list) or any(not isinstance(v, str) or
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v) or v.startswith("ICLAYOUT_BENCH_") for v in variables)):
        raise ValueError("env_vars must name non-session environment variables")
    executable = str((base / argv[0]).absolute()) if "/" in argv[0] else shutil.which(argv[0])
    if not executable or not Path(executable).is_file():
        raise ValueError("Participant executable not found: " + argv[0])
    contents = {name: hashlib.sha256(read_file(base, name)).hexdigest() for name in files}
    resolved = [executable, *[str(base / arg) if arg in contents else arg for arg in argv[1:]]]
    return {"command": resolved, "files": {str(base / name): sha for name, sha in contents.items()},
            "env_vars": variables, "identity": {"command": argv, "files": contents,
            "executable": hashlib.sha256(Path(executable).read_bytes()).hexdigest(), "env_vars": variables}}


def resolve_scheme(value, base, harness):
    if not isinstance(value, dict) or set(value) - {"instructions", "solver_image", "launch", "version", "mcp"}:
        raise ValueError("Unknown participant scheme fields")
    result = dict(value)
    if not isinstance(value.get("instructions", ""), str):
        raise TypeError("scheme.instructions must be text")
    image = value.get("solver_image")
    if image is not None and (not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image)):
        raise ValueError("scheme.solver_image must be an immutable Docker image ID (sha256:...)")
    if harness == "command":
        if not isinstance(value.get("version"), str) or not value["version"]:
            raise ValueError("Command participants must declare scheme.version")
        result["launch"] = launch_spec(value.get("launch"), base)
    elif "launch" in value or "version" in value:
        raise ValueError("scheme.launch and version belong to command participants")
    mcp = value.get("mcp", {})
    if not isinstance(mcp, dict):
        raise TypeError("scheme.mcp must be a table of stdio tools")
    result["mcp"] = {}
    for name, spec in mcp.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name) or name == "layout":
            raise ValueError("Invalid or reserved MCP name: " + name)
        result["mcp"][name] = launch_spec(spec, base)
    return result


def identity(scheme):
    return {**{k: v for k, v in scheme.items() if k not in {"launch", "mcp"}},
            **({"launch": scheme["launch"]["identity"]} if "launch" in scheme else {}),
            "mcp": {k: v["identity"] for k, v in scheme.get("mcp", {}).items()}}


def check(scheme):
    for spec in [*scheme.get("mcp", {}).values(), *([scheme["launch"]] if "launch" in scheme else [])]:
        missing = set(spec["env_vars"]) - os.environ.keys()
        if missing:
            raise ValueError("Missing participant environment variables: " + ", ".join(sorted(missing)))
        if hashlib.sha256(Path(spec["command"][0]).read_bytes()).hexdigest() != spec["identity"]["executable"]:
            raise ValueError("Participant executable changed after configuration")
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in spec["files"].items()):
            raise ValueError("Participant tool files changed after configuration")


def mcp_servers(scheme, session_env):
    check(scheme)
    servers = {}
    for name, spec in scheme.get("mcp", {}).items():
        servers[name] = {"command": spec["command"][0], "args": spec["command"][1:],
                         "env": {**{k: os.environ[k] for k in spec["env_vars"]}, **session_env}}
    return servers
