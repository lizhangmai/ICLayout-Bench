"""Detached experiment coordinator entry point."""

import json
import sys
from pathlib import Path


def main():
    from benchmarking.participants.batch.runner import BatchOptions, execute_condition
    from benchmarking.participants.harnesses.contracts import ParticipantSelection

    payload = json.load(sys.stdin)
    options = payload['options']
    if options['results_data']:
        options['results_data'] = Path(options['results_data'])
    code = execute_condition(BatchOptions(**options), payload['row'],
        ParticipantSelection(**payload['selection']), Path(payload['output']), payload['identity'], set(),
        scheduler_fd=int(sys.argv[1]))
    return code


if __name__ == '__main__':
    sys.exit(main())
