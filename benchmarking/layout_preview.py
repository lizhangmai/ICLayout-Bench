"""Export final submitted layout PNGs from local experiment archives, without model calls."""

import argparse
import json
import re
import struct
import subprocess
from pathlib import Path

from .engine.docker import DockerTool
from .engine.recorder import BatchLease
from .files import Asset, atomic_write, read_file, relative
from .participants.storage import CaseLease


def archived_asset(root, record):
    asset = Asset(read_file(root, record["path"]), record["format"])
    if asset.sha256 != record["sha256"] or len(asset.content) != record["bytes"]:
        raise ValueError("Archived asset identity mismatch")
    return asset


def export_layout(case_dir):
    """Caller holds the batch lease. Never alter the result or candidate evidence."""
    case_dir = Path(case_dir)
    compact_path = case_dir / "result.json"
    compact = json.loads(compact_path.read_text()) if compact_path.exists() else None
    if compact is not None:
        result = compact.get("evaluation") or {}
        if not (case_dir / "final.gds").exists():
            return {"status": "unavailable", "reason": "no_local_final_candidate"}
        candidate = Asset(read_file(case_dir, "final.gds"), "gds")
        if (result.get("submission") or {}).get("candidate_sha256") and candidate.sha256 != result["submission"]["candidate_sha256"]:
            raise ValueError("Final GDS does not match scored submission")
        top_cell = compact["top_cell"]
        previous = compact.get("image") or {}
    else:
        result_path = case_dir / "participant" / "analysis" / "result.json"
        if not result_path.exists():
            return {"status": "unavailable", "reason": "no_terminal_result"}
        result = json.loads(result_path.read_text())
        if result.get("state") not in {"complete", "error"} or not result.get("submission"):
            return {"status": "unavailable", "reason": "no_final_submission"}
        sid = result["session_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", sid):
            raise ValueError("Invalid archived session ID")
        archive = case_dir / "service" / "service-store" / sid / "run"
        if not archive.is_dir():
            return {"status": "unavailable", "reason": "local_candidate_archive_unavailable"}
        record = json.loads((archive / "run.json").read_text())
        candidate = archived_asset(archive, record["candidate"])
        if candidate.sha256 != result["submission"]["candidate_sha256"]:
            raise ValueError("Final submission does not match archived candidate")
        task = json.loads(archived_asset(archive, record["task"]).content)
        if task["task_sha256"] != result["task_sha256"]:
            raise ValueError("Frozen task identity mismatch")
        top_cell = task["output"]["top_cell"]
        previous = {}
    image_path, metadata_path = case_dir / "layout.png", case_dir / "layout-preview.json"
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
    lean = compact is not None and compact.get("schema_version") in {2, 3}
    if lean and previous.get("status") == "complete" and image_path.exists():
        return previous
    if not lean and previous.get("status") == "complete":
        if previous["candidate_sha256"] != candidate.sha256:
            raise ValueError("Existing preview belongs to a different candidate")
        if image_path.exists() and Asset(image_path.read_bytes(), "png").sha256 == previous["png_sha256"]:
            return previous
    image_id = result["tool_identity"]["image_id"]
    tool = DockerTool(image_id, ["python", "-c", "import klayout.db as k; print(k.__version__)"], 120)
    script = Path(__file__).parent / "engine" / "layout_image.py"
    rendered = tool.run(["python", "-I", "render.py"], {
        "candidate.gds": candidate, "render.py": Asset(script.read_bytes(), "python"),
        "settings.json": Asset(json.dumps({"top_cell": top_cell}).encode(), "json"),
    }, {"layout.png": "png", "image.json": "json"})
    if rendered.returncode != 0 or rendered.reason:
        raise RuntimeError("Layout renderer failed or timed out")
    png = rendered.files["layout.png"]
    info = json.loads(rendered.files["image.json"].content)
    if (png.content[:8] != b"\x89PNG\r\n\x1a\n" or len(png.content) < 24
            or struct.unpack(">II", png.content[16:24]) != (info["width"], info["height"])):
        raise ValueError("Renderer produced an invalid PNG")
    metadata = {"status": "complete", "schema_version": 1, "candidate_sha256": candidate.sha256,
                "submission_id": result["submission"]["submission_id"],
                "png_sha256": png.sha256, "image_id": image_id,
                "renderer_sha256": Asset(script.read_bytes(), "python").sha256, **info}
    atomic_write(image_path, png.content)
    if compact is not None:
        if lean:
            metadata = {"status": "complete", **info}
            if "layout.png" not in compact["files"]:
                compact["files"].append("layout.png")
        else:
            compact.setdefault("files", {})["layout.png"] = png.sha256
        compact["image"] = metadata
        atomic_write(compact_path, (json.dumps(compact, indent=2) + "\n").encode())
    else:
        atomic_write(metadata_path, (json.dumps(metadata, indent=2) + "\n").encode())
    return metadata


def ensure_layout_preview(case_dir):
    """Preview failures are visible but cannot turn a completed experiment into a failure."""
    try:
        status = export_layout(case_dir)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        status = {"status": "error", "error_type": type(error).__name__}
        # Do not copy Docker diagnostics, credentials or host paths into shareable metadata.
        try:
            path = Path(case_dir) / "result.json"
            if path.exists():
                compact = json.loads(path.read_text())
                compact["image"] = status
                atomic_write(path, (json.dumps(compact, indent=2) + "\n").encode())
            else:
                atomic_write(Path(case_dir) / "layout-preview-error.json",
                             (json.dumps(status) + "\n").encode())
        except OSError:
            pass  # An unwritable preview directory must not invalidate a scored result.
        print(f"LAYOUT_PREVIEW error={type(error).__name__} case={case_dir}; retry with benchmarking.layout_preview",
              flush=True)
        return status
    if status["status"] == "complete":
        print(f"LAYOUT_PREVIEW path={Path(case_dir) / 'layout.png'}", flush=True)
    else:
        print(f"LAYOUT_PREVIEW unavailable={status['reason']} case={case_dir}", flush=True)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Existing case, condition directory or legacy batch")
    args = parser.parse_args()
    errors = False
    compact_slots = ([args.batch] if (args.batch / "result.json").is_file() else
                     sorted(p.parent for p in args.batch.glob("*/result.json")) +
                     sorted(p.parent for p in args.batch.glob("*/repetition-*/result.json")))
    if compact_slots:
        for slot in compact_slots:
            case = slot.parent if slot.name.startswith("repetition-") else slot
            with CaseLease(case):
                errors |= ensure_layout_preview(slot)["status"] == "error"
    elif (args.batch / "case.json").is_file() or list(args.batch.glob("*/case.json")):
        cases = ([args.batch] if (args.batch / "case.json").is_file()
                 else sorted(p.parent for p in args.batch.glob("*/case.json")))
        for case in cases:
            with CaseLease(case):
                manifest = json.loads((case / "case.json").read_text())
                repetitions = manifest["identity"]["plan"][0]["repetitions"]
                for repetition in range(1, repetitions + 1):
                    slot = case if repetitions == 1 else case / f"repetition-{repetition}"
                    summary = slot / "summary.json"
                    if summary.exists() and json.loads(summary.read_text()).get("state") == "finished":
                        errors |= ensure_layout_preview(slot)["status"] == "error"
    else:
        with BatchLease(args.batch):
            for row in json.loads((args.batch / "summary.json").read_text()):
                if row.get("state", "finished") == "finished":
                    directory = row["directory"]
                    relative(directory, "case directory")
                    errors |= ensure_layout_preview(args.batch / directory)["status"] == "error"
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
