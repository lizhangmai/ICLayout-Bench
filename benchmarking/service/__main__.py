"""Run the local development service against a Dataset case."""
import argparse
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from benchmarking.dataset import load_dataset
from benchmarking.engine.runtime import load_case
from benchmarking.engine.source import implementation_identity
from benchmarking.files import append_event, write_json

from .process import process_start
from .server import LocalService, serve

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset', required=True)
parser.add_argument('--revision')
parser.add_argument('--case', required=True)
parser.add_argument('--dataset-name')
parser.add_argument('--dataset-split', default='test')
parser.add_argument('--offline', action='store_true')
parser.add_argument('--data', type=Path, required=True)
parser.add_argument('--image', default='iclayout-eda-open:local')
parser.add_argument('--solver-image', help='Separate solver image; evaluator keeps --image')
parser.add_argument('--solver-runtime', help='Explicit operator external runtime for solver mounts')
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--owner-record', type=Path, help=argparse.SUPPRESS)
parser.add_argument('--token-env', default='ICLAYOUT_BENCH_ACCESS_TOKEN')
args = parser.parse_args()
token = os.environ.get(args.token_env)
if not token:
    parser.error('Access token environment variable is required')
dataset = load_dataset(args.dataset, revision=args.revision, local_files_only=args.offline)
with redirect_stdout(sys.stderr):
    config = (dataset.native_cases(args.dataset_name, args.dataset_split)[1][args.case]
              if args.dataset_name else dataset.case(args.case))
    runtime = load_case(config, image=args.image)
solver_runtime = None
if args.solver_runtime:
    if runtime.external is None or runtime.external.name != args.solver_runtime:
        parser.error('Solver runtime must match the external process declaration')
    solver_runtime = runtime.external
revision = implementation_identity()
service = LocalService(args.data, runtime.task, {} if solver_runtime else runtime.agent_resources(),
                       runtime.backends, args.solver_image or (solver_runtime.image if solver_runtime else args.image),
                       token, revision=revision, solver_runtime=solver_runtime)
server = serve(service, args.port, audit=args.data / 'http.jsonl')
endpoint = f'http://127.0.0.1:{server.server_port}'
try:
    append_event(args.data / 'lifecycle.jsonl', 'service_started', durable=True, pid=os.getpid())
    if args.owner_record:
        args.owner_record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_json(args.owner_record, {'pid': os.getpid(), 'start': process_start(os.getpid()),
                                       'endpoint': endpoint})
    print(f'Local development service: {endpoint}', flush=True)
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
    service.shutdown()
    append_event(args.data / 'lifecycle.jsonl', 'service_stopped', durable=True, pid=os.getpid())
