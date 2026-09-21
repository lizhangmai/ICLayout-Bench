"""Version-bound circuit drawings and optional KLayout geometry, never solver inputs."""

import json
import math
import re
import subprocess
import tomllib
from html import escape
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from sqlalchemy import select

from . import schema as s
from .store import digest


def reader_summary(case):
    """Read browsing metadata directly from the current task contract."""
    fields = case.get("presentation", {})
    return {"title": case.get("title", ""), "category": fields.get("category", "Other circuits"),
            "summary": fields.get("summary", "")}


def parse_netlist(text, subcircuit):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+") and lines:
            lines[-1] += " " + line[1:]
        else:
            lines.append(line)
    active, ports, devices = False, [], []
    for line in lines:
        # CDL permits dollar signs in instance and node names (Q$1, $10).
        # Only a standalone dollar comment marker terminates the card.
        words = re.split(r"\s+\$(?:\s|$)", line, maxsplit=1)[0].split()
        if not words:
            continue
        if words[0].lower() == ".subckt":
            active = words[1].lower() == subcircuit.lower()
            if active:
                ports = [
                    p for p in words[2:] if "=" not in p and p.lower() != "params:"
                ]
            continue
        if words[0].lower() == ".ends":
            if active:
                return {"subcircuit": subcircuit, "ports": ports, "devices": devices}
            continue
        if not active or words[0].startswith("."):
            continue
        name, kind = words[0], words[0][0].upper()
        count = {
            "M": 4,
            "R": 2,
            "C": 2,
            "L": 2,
            "D": 2,
            "Q": 3,
            "V": 2,
            "I": 2,
            "B": 2,
        }.get(kind)
        words = [w for w in words if w != "/"]
        if kind in {"X", "Q", "R"}:
            end = next(
                (i for i, w in enumerate(words) if "=" in w or w.lower() == "params:"),
                len(words),
            )
            if kind == "X":
                count = end - 2
            elif (kind, end) in {("Q", 6), ("R", 5)} and not re.match(
                r"^[+-]?(?:\d|\.\d)", words[end - 1]
            ):
                # Model-backed CDL HBT/resistor cards may carry an explicit substrate.
                # A trailing numeric SPICE area/value remains a parameter, not a pin.
                count += 1
        if not count or len(words) < count + 2:
            raise ValueError("Unsupported or malformed netlist device: " + name)
        devices.append(
            {
                "name": name,
                "kind": kind,
                "nodes": words[1 : count + 1],
                "model": words[count + 1],
                "parameters": " ".join(words[count + 2 :]),
            }
        )
    raise ValueError("Target subcircuit is missing or unterminated: " + subcircuit)


def schematic_svg(circuit):
    """Net-label schematic: equal labels denote an electrical connection, including bodies."""
    devices = circuit["devices"]
    columns = min(3, max(1, len(devices)))
    width, height = columns * 390, 130 + math.ceil(len(devices) / columns) * 260
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<g font-family="monospace" fill="#172554" font-size="14">',
        f'<text x="24" y="32" font-size="21">{escape(circuit["subcircuit"])}</text>',
        '<text x="24" y="58">Netlist-generated schematic · equal net labels are connected</text>',
    ]
    for i in range(0, len(circuit["ports"]), 12):
        elements.append(
            f'<text x="24" y="{82 + i * 2}">Ports: {escape(" · ".join(circuit["ports"][i : i + 12]))}</text>'
        )
    for i, device in enumerate(devices):
        x, y = (i % columns) * 390 + 15, (i // columns) * 260 + 115
        elements += [
            f'<g transform="translate({x},{y})">',
            '<rect width="360" height="242" rx="12" fill="white" stroke="#cbd5e1"/>',
            f'<text x="16" y="27" font-weight="bold">{escape(device["name"])} · {escape(device["model"])}</text>',
        ]
        nodes = device["nodes"]
        if device["kind"] == "M":
            elements.append(
                '<path d="M150 75 V155 M158 75 V155 M158 87 H194 V58 M158 145 H194 V175 M100 115 H150 M158 115 H250" fill="none" stroke="#2563eb" stroke-width="3"/>'
            )
            for label, node, px, py in zip(
                ("D", "G", "S", "B"), nodes, (194, 22, 194, 248), (50, 108, 194, 108)
            ):
                elements.append(
                    f'<text x="{px}" y="{py}" font-size="12">{label}: {escape(node)}</text>'
                )
        else:
            # Explicit pin numbers preserve ordering for subcircuits and other devices.
            elements.append(
                '<rect x="115" y="66" width="125" height="75" rx="4" fill="#eff6ff" stroke="#2563eb"/>'
            )
            elements.append(f'<text x="145" y="106">{escape(device["kind"])}</text>')
            for j, node in enumerate(nodes):
                elements.append(
                    f'<text x="16" y="{160 + j * 15}" font-size="12">{j + 1}: {escape(node)}</text>'
                )
        elements.append(
            f'<text x="16" y="226" font-size="11">{escape(device["parameters"][:53])}</text></g>'
        )
    return ("".join(elements) + "</g></svg>").encode()


def case_schematic(task_id, path, data, read):
    """Validate a case-owned SVG against its declared circuit and content digests."""
    netlist_sha256 = data["task"]["inputs"]["netlist"]["sha256"]
    drawings = [a for a in data.get("assets", []) if a["role"] == "schematic"]
    if not drawings:
        return None
    if len(drawings) != 1:
        raise ValueError("Expected one declared schematic per case")
    asset = drawings[0]
    if asset["format"] != "svg":
        raise ValueError("Schematic must be SVG")
    svg = read(str(PurePosixPath(path).parent / asset["path"]))
    if digest(svg) != asset["sha256"]:
        raise ValueError("Schematic digest mismatch")
    try:
        root = ElementTree.fromstring(svg)
        metadata = json.loads(
            root.findtext("{http://www.w3.org/2000/svg}metadata", "")
        )
    except (ElementTree.ParseError, json.JSONDecodeError) as error:
        raise ValueError("Schematic provenance metadata is invalid") from error
    if root.tag != "{http://www.w3.org/2000/svg}svg" or not isinstance(
        metadata, dict
    ):
        raise ValueError("Schematic must carry SVG provenance")
    if (
        metadata.get("format") != "iclayout-schematic"
        or metadata.get("case_id") != task_id
        or metadata.get("netlist_sha256") != netlist_sha256
    ):
        raise ValueError("Schematic provenance does not match the recorded circuit")
    return svg, {
        "kind": "authored",
        "schematic_path": str(PurePosixPath(path).parent / asset["path"]),
        "schematic_sha256": digest(svg),
    }


class GitCatalog:
    def __init__(self, root, revision):
        self.root = Path(root)
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision or ""):
            raise ValueError(
                "A recorded full Git commit is required for catalog binding"
            )
        self.revision = revision
        self.paths = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "ls-tree",
                "-r",
                "--name-only",
                revision,
                "--",
                "tasks",
            ],
            text=True,
        ).splitlines()
        self.cases = {}
        for path in self.paths:
            if path.endswith("/case.toml"):
                data = tomllib.loads(self.read(path).decode())
                self.cases[data["id"]] = (path, data)

    def read(self, path):
        if ".." in PurePosixPath(path).parts or path.startswith("/"):
            raise ValueError("Invalid catalog path")
        return subprocess.check_output(
            ["git", "-C", str(self.root), "show", f"{self.revision}:{path}"],
            stderr=subprocess.PIPE,
        )

    def schematic(self, task_id, netlist_sha256):
        """Read a declared, digest-bound drawing without rebinding historical tasks."""
        if task_id not in self.cases:
            return None
        path, data = self.cases[task_id]
        if data["task"]["inputs"]["netlist"]["sha256"] != netlist_sha256:
            raise ValueError("Authored schematic belongs to a different netlist")
        drawing = case_schematic(task_id, path, data, self.read)
        if drawing:
            drawing[1]["schematic_commit"] = self.revision
        return drawing

    def attach(self, store, task, schematic_catalog=None):
        path, data = self.cases[task["task_id"]]
        recorded_digest = task["identity"].get("task_sha256")
        if recorded_digest and digest(self.read(path)) != recorded_digest:
            raise ValueError(
                "Recorded task hash differs from catalog case; refusing schematic binding"
            )
        base = PurePosixPath(path).parent
        entry = data["task"]["inputs"]["netlist"]
        source = base / entry.get("source", entry["path"])
        raw = self.read(str(source))
        if digest(raw) != entry["sha256"]:
            raise ValueError("Catalog netlist digest mismatch")
        circuit = parse_netlist(raw.decode(), entry["subcircuit"])
        authored = (schematic_catalog or self).schematic(task["task_id"], digest(raw))
        store.attach(
            task["id"],
            "schematic.svg",
            authored[0] if authored else schematic_svg(circuit),
            task=True,
        )
        store.attach(
            task["id"], "circuit.json", json.dumps(circuit).encode(), task=True
        )
        store.attach(task["id"], "circuit.spice", raw, task=True)
        # Preserve collection licensing and source attribution with the derivative.
        collection = str(base.parent.parent) + "/"
        for asset in self.paths:
            if (
                asset.startswith(collection)
                and "/" not in asset[len(collection) :]
                and re.search(r"license|notice|copying", asset, re.IGNORECASE)
            ):
                store.attach(
                    task["id"], PurePosixPath(asset).name, self.read(asset), task=True
                )
        metadata = {
            "kind": "netlist_generated",
            "commit": self.revision,
            "case_path": path,
            "netlist_sha256": digest(raw),
            "source": data.get("source", data.get("origin")),
            "binding": "task_digest" if recorded_digest else "recorded_release",
            "note": "Release-bound presentation; absent historical task hashes remain unknown.",
        }
        if authored:
            metadata.update(authored[1])
        store.attach(
            task["id"], "source.json", json.dumps(metadata).encode(), task=True
        )
        with store.engine.begin() as conn:
            conn.execute(
                s.tasks.update()
                .where(s.tasks.c.id == task["id"])
                .values(
                    title=data.get("title"),
                    pdk=PurePosixPath(path).parts[1],
                    presentation=metadata,
                )
            )
        return {
            "task_id": task["task_id"],
            "status": "attached",
            "devices": len(circuit["devices"]),
        }


class SnapshotCatalog(GitCatalog):
    def __init__(self, source, revision):
        from benchmarking.dataset import load_dataset
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision or ""):
            raise ValueError("A recorded full Dataset commit is required for catalog binding")
        dataset = load_dataset(source, revision=revision)
        self.root, self.revision = dataset.root, dataset.identity["commit"]
        self.paths = [p.relative_to(self.root).as_posix()
                      for p in (self.root / "tasks").rglob("*") if p.is_file()]
        self.cases = {name: (path.relative_to(self.root).as_posix(),
                            tomllib.loads(path.read_text()))
                      for name, path in dataset.cases().items()}

    def read(self, path):
        from benchmarking.files import read_file
        return read_file(self.root, path)


def attach_catalog(store, root, *, schematic_revision=None):
    catalog_type = GitCatalog if Path(root).is_dir() else SnapshotCatalog
    cache, results = {}, []
    schematic_catalog = (
        catalog_type(root, schematic_revision) if schematic_revision else None
    )
    with store.engine.connect() as conn:
        tasks = list(conn.execute(select(s.tasks)).mappings())
    for task in tasks:
        revision = (task["identity"].get("dataset") or {}).get("commit")
        try:
            if revision not in cache:
                cache[revision] = catalog_type(root, revision)
            results.append(cache[revision].attach(store, task, schematic_catalog))
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            results.append({"task_id": task["task_id"], "status": "unavailable",
                            "reason": str(error)})
    return results
