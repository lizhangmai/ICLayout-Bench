"""Version-bound task materials and browsing metadata, never solver inputs."""

import json
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath

from .normalization import digest


def reader_summary(case):
    """Read browsing metadata directly from the current task contract."""
    fields = case.get("presentation", {})
    return {"title": case.get("title", ""), "category": fields.get("category", "Other circuits"),
            "summary": fields.get("summary", "")}


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

    def attach(self, store, task):
        path, data = self.cases[task["task_id"]]
        recorded_digest = task["identity"].get("task_sha256")
        if recorded_digest and digest(self.read(path)) != recorded_digest:
            raise ValueError(
                "Recorded task hash differs from catalog case; refusing material binding"
            )
        base = PurePosixPath(path).parent
        entry = data["task"]["inputs"]["netlist"]
        source = base / entry.get("source", entry["path"])
        raw = self.read(str(source))
        if digest(raw) != entry["sha256"]:
            raise ValueError("Catalog netlist digest mismatch")
        store.attach(task["id"], "circuit.spice", raw, task=True)
        # Preserve collection licensing and source attribution with task materials.
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
            "kind": "catalog",
            "commit": self.revision,
            "case_path": path,
            "netlist_sha256": digest(raw),
            "source": data.get("source", data.get("origin")),
            "binding": "task_digest" if recorded_digest else "recorded_release",
            "note": "Release-bound presentation; absent historical task hashes remain unknown.",
        }
        store.attach(
            task["id"], "source.json", json.dumps(metadata).encode(), task=True
        )
        store.update_task_presentation(task["id"], title=data.get("title"),
                                       pdk=PurePosixPath(path).parts[1], metadata=metadata)
        return {
            "task_id": task["task_id"],
            "status": "attached",
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


def attach_catalog(store, root):
    catalog_type = GitCatalog if Path(root).is_dir() else SnapshotCatalog
    cache, results = {}, []
    tasks = store.inventory()["tasks"]
    for task in tasks:
        revision = (task["identity"].get("dataset") or {}).get("commit")
        try:
            if revision not in cache:
                cache[revision] = catalog_type(root, revision)
            results.append(cache[revision].attach(store, task))
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            results.append({"task_id": task["task_id"], "status": "unavailable",
                            "reason": str(error)})
    return results
