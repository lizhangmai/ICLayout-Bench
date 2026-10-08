"""Render scored candidate snapshots without owning participant runtime or locks."""

import json
import struct
import subprocess
from pathlib import Path

from benchmarking.engine.source import package_source
from benchmarking.engine.tools.docker import DockerTool
from benchmarking.files import Asset, atomic_write, read_file


def export_layout(case_dir, *, image=None):
    """Caller holds the case lease. Never alter the result or candidate evidence."""
    case_dir = Path(case_dir)
    compact_path = case_dir / "result.json"
    if not compact_path.is_file():
        return {"status": "unavailable", "reason": "no_terminal_result"}
    compact = json.loads(compact_path.read_text())
    if compact.get("format") != "participant-result":
        raise ValueError("Unsupported participant result format")
    result = compact.get("evaluation") or {}
    if not (case_dir / "final.gds").exists():
        return {"status": "unavailable", "reason": "no_local_final_candidate"}
    candidate = Asset(read_file(case_dir, "final.gds"), "gds")
    if (result.get("submission") or {}).get("candidate_sha256") and candidate.sha256 != result["submission"]["candidate_sha256"]:
        raise ValueError("Final GDS does not match scored submission")
    top_cell = compact["top_cell"]
    previous = compact.get("image") or {}
    image_path = case_dir / "layout.png"
    if previous.get("status") == "complete" and image_path.exists():
        return previous
    image_id = image or result["tool_identity"]["image_id"]
    tool = DockerTool(image_id, ["python", "-c", "import klayout.db as k; print(k.__version__)"], 120)
    script = package_source("engine/container_scripts/layout_image.py")
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
    metadata = {"status": "complete", **info, "renderer_image_id": tool.image_id}
    atomic_write(image_path, png.content)
    if "layout.png" not in compact["files"]:
        compact["files"].append("layout.png")
    compact["image"] = metadata
    atomic_write(compact_path, (json.dumps(compact, indent=2) + "\n").encode())
    return metadata


def ensure_layout_preview(case_dir, *, image=None):
    """Preview failures are visible but cannot turn a completed experiment into a failure."""
    try:
        status = export_layout(case_dir, image=image)
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
