"""Export structured analysis of explicitly supplied participant or HTTP results."""

import argparse
import json
from pathlib import Path

from benchmarking.results.analysis import export_participant_results, export_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    results = []
    for path in args.inputs:
        path = path / "result.json" if path.is_dir() else path
        data = json.loads(path.read_bytes())
        if isinstance(data, dict) and "results" in data:
            results.extend(data["results"])
        else:
            results.extend(data if isinstance(data, list) else [data])
    participant = [r.get("format") == "participant-result" for r in results]
    if any(participant) and not all(participant):
        parser.error("Analyze participant exports and service results separately")
    exporter = export_participant_results if all(participant) else export_results
    print(exporter(results, args.output))


if __name__ == "__main__":
    main()
