"""Manage a portable results database and copied attachments."""

import argparse
import json
import os
from pathlib import Path

from .store import ResultStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--database-url-env", default="ICLAYOUT_BENCH_DATABASE_URL")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser(
        "import", help="Copy terminal results and artifacts into the archive"
    )
    importer.add_argument("source", type=Path)
    importer.add_argument("--experiment")
    importer.add_argument("--namespace", default="local")
    importer.add_argument("--reevaluation", action="store_true")
    catalog = commands.add_parser(
        "catalog", help="Attach schematics from each recorded Dataset revision"
    )
    catalog.add_argument("--dataset", required=True)
    catalog.add_argument(
        "--schematic-revision",
        help="Full Git commit containing authored SVGs; must match each recorded netlist digest",
    )
    geometry = commands.add_parser(
        "geometry", help="Generate optional layer geometry (requires klayout)"
    )
    geometry.add_argument("--run")
    commands.add_parser("verify", help="Verify every stored artifact digest")
    commands.add_parser(
        "retry", help="Retry the durable runner outbox without model calls"
    )
    commands.add_parser("list", help="List runs")
    args = parser.parse_args(argv)
    if args.command == "retry":
        from benchmarking.participants.archive import retry

        result = retry(args.data)
        print(json.dumps(result, indent=2))
        return int(any(r["status"] == "pending" for r in result))
    store = ResultStore(args.data, database_url=os.environ.get(args.database_url_env))
    try:
        if args.command == "import":
            result = store.import_directory(
                args.source,
                experiment=args.experiment or args.source.name,
                namespace=args.namespace,
                reevaluation=args.reevaluation,
            )
        elif args.command == "catalog":
            from .presentation import attach_catalog

            result = attach_catalog(
                store, args.dataset, schematic_revision=args.schematic_revision
            )
        elif args.command == "geometry":
            from .geometry import attach_geometry

            result = attach_geometry(store, run_id=args.run)
        elif args.command == "verify":
            result = store.verify()
        else:
            result = store.list_runs()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return (
            int(any(r.get("status") in {"error", "unavailable"} for r in result))
            if isinstance(result, list)
            else int(bool(result.get("failures")))
        )
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
