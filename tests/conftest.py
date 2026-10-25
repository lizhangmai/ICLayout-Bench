"""Runtime fixtures shared by HTTP protocol and explicit capacity acceptance."""

import os
import threading

import pytest

from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.eda.runtime import load_case
from benchmarking.service.server import LocalService, serve
from benchmarking.tasks.dataset import load_dataset


@pytest.fixture
def host(tmp_path):
    dataset = load_dataset(os.environ.get('ICLAYOUT_BENCH_DATASET'))
    case = os.environ.get('ICLAYOUT_BENCH_CASE', 'freepdk45.nangate45-pdk.NAND2_X1')
    image = os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', DEFAULT_IMAGE)
    runtime = load_case(dataset.case(case), image=image)
    service = LocalService(tmp_path/'store', runtime.task, runtime.agent_resources(), runtime.backends,
                           image, 'operator-test')
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    endpoint = f'http://127.0.0.1:{server.server_port}'
    yield service, endpoint
    server.shutdown()
    server.server_close()
    thread.join()
    service.shutdown()
