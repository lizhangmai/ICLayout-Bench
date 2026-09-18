"""Evaluate declared public witnesses through their own plans and resource bindings."""

import os
import tomllib

import pytest
from helpers.catalog import CATALOGS, ROOT, read_catalog

from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.preparation import prepare_case as prepare_public_case
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.files import Asset, read_file
from benchmarking.tasks import load_task

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]
CASES = [path for catalog in CATALOGS for path, data in read_catalog(catalog)[1]
         if data.get('status') in {'candidate', 'qualified'}
         and data.get('task') and data.get('qualification', {}).get('reference')]


@pytest.fixture(scope='module')
def prepare_case(tmp_path_factory):
    image = os.environ.get('ICLAYOUT_BENCH_TEST_IMAGE', 'iclayout-bench-tools:local')
    environments = {}

    def prepare(case):
        if case in environments:
            return environments[case]
        prepared = prepare_public_case(case, tmp_path_factory.mktemp('public-reference') / 'prepared',
                                       root=ROOT, image=image)
        data = tomllib.loads(prepared.read_text())
        witness_path = data['qualification']['reference']
        witness = Asset(read_file(prepared.parent, witness_path), 'gds')
        environments[case] = load_task(prepared), load_toolchain(prepared), witness
        return environments[case]

    return prepare


@pytest.fixture(params=CASES, ids=lambda p: str(p.relative_to(ROOT / 'tasks').parent))
def case_environment(request, prepare_case):
    return prepare_case(request.param)


def evaluate(environment, candidate, output):
    task, backends, _ = environment
    return run_evaluation(task.evaluation, {**task.evaluation_inputs(), 'candidate': candidate},
                          backends, output, task_sha256=task.digest, task_witnessed=task.witnessed)


def test_published_witness_satisfies_its_declared_contract(case_environment, tmp_path):
    witness = case_environment[2]
    report = evaluate(case_environment, witness, tmp_path / 'reference')
    assert report['task_success'] is True, report
    assert report['inputs']['candidate']['sha256'] == witness.sha256


def test_empty_candidate_cannot_satisfy_a_layout_task(case_environment, tmp_path):
    db = pytest.importorskip('klayout.db')
    task = case_environment[0]
    layout = db.Layout()
    layout.create_cell(task.output.top_cell)
    options = db.SaveLayoutOptions()
    options.format = 'GDS2'
    candidate = Asset(layout.write_bytes(options), 'gds')
    report = evaluate(case_environment, candidate, tmp_path / 'empty')
    assert report['physical_valid'] is False, report
    assert report['score']['value'] == 0


# Use maintained standard cells and their native LVS databases. A changed frame
# requirement is an independent geometric counterexample; no synthetic transistor
# circuit or duplicated process-layer constants are needed.
FRAME_CASES = [case for case in CASES if any(
    item['type'] == 'cell_frame'
    for item in tomllib.loads(case.read_text())['task']['constraints']['hard'])]


@pytest.mark.parametrize('case', FRAME_CASES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize('violation', ['height', 'width_grid', 'rail'])
def test_standard_cell_frame_rejects_incompatible_row_contract(case, violation, prepare_case, tmp_path):
    import json

    task, backends, witness = prepare_case(case)
    inputs = task.evaluation_inputs()
    constraints = json.loads(inputs['input:constraints'].content)
    frame = next(spec for spec in constraints['hard'] if spec['type'] == 'cell_frame')
    if violation == 'height':
        frame['height_um'] *= 2
    elif violation == 'width_grid':
        # A positive width below this grid cannot be an integer grid multiple.
        outline = next(spec for spec in constraints['hard'] if spec['type'] == 'bbox_max')
        frame['width_grid_um'] = 2 * outline['max_width_um']
    else:
        # A rail beyond the functional box cannot cover its required strip.
        frame['rails'][0]['y_um'] = 2 * frame['height_um']
    inputs['input:constraints'] = Asset(json.dumps(constraints).encode(), 'json')
    report = run_evaluation(task.evaluation, {**inputs, 'candidate': witness}, backends, tmp_path / 'invalid-frame')
    assert report['jobs']['lvs']['status'] == 'passed'
    assert report['jobs']['geometry']['status'] == 'failed'
    assert report['score']['value'] == 0
