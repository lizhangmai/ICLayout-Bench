"""Run the local development service against a prepared public case."""
import argparse
import os
from pathlib import Path

from benchmarking.bundles import load_bundle
from benchmarking.engine.source import implementation_identity
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.files import Asset
from benchmarking.tasks import load_task

from .server import LocalService, serve

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prepared', type=Path, required=True)
parser.add_argument('--data', type=Path, required=True)
parser.add_argument('--image', default='iclayout-bench-tools:dev')
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--token-env', default='ICLAYOUT_BENCH_ACCESS_TOKEN')
args = parser.parse_args()
token = os.environ.get(args.token_env)
if not token:
    parser.error('Access token environment variable is required')
case = args.prepared.resolve()/'case/case.toml'
bundle = load_bundle(args.prepared.resolve()/'agent-resources')
revision = implementation_identity()
service = LocalService(args.data,load_task(case),dict(bundle.files)|{'manifest.json':Asset(bundle.manifest.content,'json')},
                       load_toolchain(case),args.image,token,revision=revision)
server = serve(service,args.port)
print(f'Local development service: http://127.0.0.1:{server.server_port}',flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
    service.shutdown()
