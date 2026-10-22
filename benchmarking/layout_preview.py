"""Export final submitted layout PNGs from local experiment archives, without model calls."""

import argparse
from pathlib import Path

from benchmarking.participants.attempt.storage import CaseLease
from benchmarking.results.preview import ensure_layout_preview, export_layout

__all__ = ["ensure_layout_preview", "export_layout", "main"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Existing case or condition directory")
    parser.add_argument("--image", help="Independent renderer image; recorded solve/evaluation identities stay unchanged")
    parser.add_argument('--pdk', type=Path, help='Explicit commercial renderer resource manifest; uses native EDA and host Ghostscript')
    args = parser.parse_args()
    if args.image and args.pdk:
        parser.error('Select --image or --pdk')
    runtime = None
    if args.pdk:
        from benchmarking.eda.environment import ExternalRuntime

        runtime = ExternalRuntime.from_manifest(args.pdk)
    errors = False
    compact_slots = ([args.batch] if (args.batch / "result.json").is_file() else
                     sorted(p.parent for p in args.batch.rglob("result.json")
                            if not any(part.startswith(".") for part in p.relative_to(args.batch).parts)))
    if compact_slots:
        for slot in compact_slots:
            case = slot.parent if slot.name.startswith("repetition-") else slot
            with CaseLease(case):
                errors |= ensure_layout_preview(slot, image=args.image, runtime=runtime)["status"] == "error"
    else:
        parser.error("No participant results found")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
