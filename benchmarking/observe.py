"""Read-only observation exports, independent of the participant's decision loop."""

import argparse
import os
from pathlib import Path

from .client import Client
from .files import Asset, atomic_write
from .protocol import json_bytes


def export_observation(client, session_id, destination, *, participant_files=()):
    """Snapshot service events and optional local traces without upgrading trust.

    Raw traces remain participant-reported, even when collected by an operator.
    They are never sent to the service. Unknown model usage remains unknown.
    """
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    offset, events = 0, []
    while True:
        page = client.observations(session_id, offset=offset)
        if page['session_id'] != session_id or page['provenance'] != 'server_observed':
            raise ValueError('Observation session/provenance mismatch')
        chunk = page['events']
        if [e['sequence'] for e in chunk] != list(range(offset, offset + len(chunk))):
            raise ValueError('Observation sequence mismatch')
        if page['next_offset'] != offset + len(chunk) or (page['has_more'] and not chunk):
            raise ValueError('Invalid observation cursor')
        events.extend(chunk)
        offset = page['next_offset']
        if not page['has_more']:
            break
    atomic_write(output / 'service-events.jsonl', b''.join(json_bytes(e) + b'\n' for e in events))
    result = client.result(session_id)
    if result['session_id'] != session_id:
        raise ValueError('Result session mismatch')
    atomic_write(output / 'service-result.json', json_bytes(result))
    traces = {}
    (output / "participant").mkdir(mode=0o700)
    for source in participant_files:
        source = Path(source)
        if source.name in traces:
            raise ValueError('Duplicate participant trace name')
        raw = source.read_bytes()
        atomic_write(output / 'participant' / source.name, raw)
        traces[source.name] = Asset(raw, 'binary').identity()
    manifest = {'session_id': session_id,
                'service': {'provenance': 'server_observed', 'available': page['available'],
                            'next_offset': offset, 'state': result['state'],
                            'verification_level': result['verification_level'],
                            'files': {name: Asset((output / name).read_bytes(), 'binary').identity()
                                      for name in ('service-events.jsonl', 'service-result.json')}},
                'participant': {'provenance': 'participant_reported', 'files': traces,
                                'coverage': 'supplied files only; internal reasoning may be unavailable'},
                'usage': result['usage'], 'usage_provenance': result['provenance'].get('usage', 'unknown')}
    atomic_write(output / 'manifest.json', json_bytes(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--participant-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    client = Client(os.environ.get('ICLAYOUT_BENCH_ENDPOINT', ''), os.environ.get('ICLAYOUT_BENCH_TOKEN', ''))
    export_observation(client, os.environ.get('ICLAYOUT_BENCH_SESSION', ''), args.output,
                       participant_files=args.participant_file)


if __name__ == '__main__':
    main()
