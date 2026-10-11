"""Export structured analysis of explicitly supplied local HTTP results."""

import argparse
import json
from pathlib import Path

from .results.analysis import export_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    results = []
    for path in args.inputs:
        data = json.loads(path.read_bytes())
        if isinstance(data, dict) and "results" in data:
            results.extend(data["results"])
        else:
            results.extend(data if isinstance(data, list) else [data])
    print(export_results(results, args.output))


if __name__ == "__main__":
    main()
