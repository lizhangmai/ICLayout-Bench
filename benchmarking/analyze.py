"""Export disclosed HTTP results or an operator-verified public rerun release."""

import argparse
import json
from pathlib import Path

from .analysis import export_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    results = []
    for path in args.inputs:
        data = json.loads(path.read_bytes())
        if isinstance(data, dict) and "results" in data:
            if data.get("dataset") != "public_development":
                raise ValueError("Hidden results require operator disclosure export")
            results.extend(data["results"])
        else:
            results.extend(data if isinstance(data, list) else [data])
    print(export_results(results, args.output, plots=args.plots))


if __name__ == "__main__":
    main()
