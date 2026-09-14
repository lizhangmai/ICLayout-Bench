"""Evaluate declared public witnesses through their own plans and resource bindings."""

import configparser
import json
import os
import tomllib

import pytest
import tomli_w
from helpers.catalog import CATALOGS, ROOT, read_catalog

from benchmarking.evaluate import run_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.prepare_support import load_profile, prepare_support
from benchmarking.tasks import load_task
from benchmarking.toolchains import load_toolchain

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]
CASES = [path for catalog in CATALOGS for path, data in read_catalog(catalog)[1]
         if data.get('status') in {'candidate', 'qualified'}
         and data.get('task') and data.get('qualification', {}).get('reference')]


@pytest.fixture(scope='module')
def prepare_case(tmp_path_factory):
    supports = {}
    image = os.environ.get('LAYOUT_BENCH_TEST_IMAGE', 'layout-bench-tools:local')
    submodules = configparser.ConfigParser()
    submodules.read(ROOT / '.gitmodules')

    def checkout(source):
        if 'checkout' in source:
            return ROOT / source['checkout']
        matches = [section['path'] for section in submodules.values()
                   if section.get('url', '').removesuffix('.git')
                   == source['repository'].removesuffix('.git')]
        assert len(matches) == 1, f'Expected one declared checkout for {source}'
        return ROOT / matches[0]

    def prepare(case):
        data = tomllib.loads(case.read_text())
        original = load_task(case)
        witness_path = data['qualification']['reference']
        witness = Asset(read_file(case.parent, witness_path), 'gds')
        for record in data.get('assets', []):
            if record['path'] == witness_path:
                assert witness.sha256 == record['sha256']
        directory = tmp_path_factory.mktemp('public-reference') / 'case'
        original.materialize(directory)
        replacements = {}
        for backend in data['toolchain']['backends'].values():
            settings = backend['settings']
            if 'image' in settings:
                settings['image'] = image
            for setting, profile in backend.get('support_profiles', {}).items():
                spec = f'{case.parents[3]}/pdk.toml#{profile}'
                if spec not in supports:
                    source = json.loads(load_profile(spec).content)['source']
                    support = tmp_path_factory.mktemp('public-support') / 'bundle'
                    prepare_support(checkout(source), spec, support, compiler_image=image)
                    supports[spec] = str(support)
                previous = replacements.setdefault(settings[setting], supports[spec])
                assert previous == supports[spec], 'Conflicting resource profile declarations'
        for backend in data['toolchain']['backends'].values():
            for setting, value in backend['settings'].items():
                if isinstance(value, str) and value in replacements:
                    backend['settings'][setting] = replacements[value]
        for entry in data['task']['inputs'].values():
            entry.pop('source', None)
            entry.pop('collection_source', None)
        prepared = directory / 'case.toml'
        prepared.write_text(tomli_w.dumps(data))
        return load_task(prepared), load_toolchain(prepared), witness

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
