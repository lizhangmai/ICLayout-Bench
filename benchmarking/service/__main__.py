"""Run the local development service against a Dataset case."""
import argparse
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from benchmarking.dataset import load_dataset
from benchmarking.engine.runtime import load_case
from benchmarking.engine.source import implementation_identity

from .server import LocalService, serve

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset', required=True)
parser.add_argument('--revision')
parser.add_argument('--case', required=True)
parser.add_argument('--dataset-name')
parser.add_argument('--dataset-split', default='test')
parser.add_argument('--offline', action='store_true')
parser.add_argument('--data', type=Path, required=True)
parser.add_argument('--image', default='iclayout-bench-tools:local')
parser.add_argument('--port', type=int, default=8765)
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
revision = implementation_identity()
service = LocalService(args.data, runtime.task, runtime.agent_resources(),
                       runtime.backends, args.image, token, revision=revision)
server = serve(service,args.port)
print(f'Local development service: http://127.0.0.1:{server.server_port}',flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
    service.shutdown()
