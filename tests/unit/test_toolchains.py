import pytest

from benchmarking.engine.toolchain_config import load_toolchain_spec
from benchmarking.engine.toolchains import load_toolchain

pytestmark = pytest.mark.unit


@pytest.fixture
def toolchain_config(tmp_path):
    def write(content, *, embedded=True):
        if embedded:
            content = ('kind = "layout_case"\n[toolchain]\n'
                       + content.replace('[', '[toolchain.'))
        path = tmp_path / "tools.toml"
        path.write_text(content)
        return path
    return write


@pytest.mark.parametrize("embedded", [False, True], ids=["standalone", "embedded"])
def test_external_adapter_can_be_bound_without_changing_task_or_evaluator(toolchain_config, embedded):
    config = toolchain_config('''
[backends.a]
type = "independent-implementation"
settings = { scale = 2 }
[backends.unused]
type = "independent-implementation"
settings = { scale = 3 }
[bindings]
"response.ac" = "a"
"response.transient" = "a"
''', embedded=embedded)
    created = []

    def factory(**settings):
        created.append(settings)
        return object()

    bindings = load_toolchain(config, factories={"independent-implementation": factory})
    assert created == [{"scale": 2}]
    assert bindings["response.ac"] is bindings["response.transient"]


def test_unknown_binding_fails_before_backend_creation(toolchain_config):
    config = toolchain_config('''
[backends.a]
type = "custom"
settings = {}
[bindings]
response = "absent"
''')

    def factory(**settings):
        pytest.fail("Invalid configuration must not initialize a tool")

    with pytest.raises(ValueError, match="unknown backend"):
        load_toolchain(config, factories={"custom": factory})


# Runtime profile binding must cover each composite support setting, including
# paths with spaces. Missing profiles fail before external tool construction.
@pytest.mark.parametrize("prepared", [False, True])
def test_composite_support_profile_metadata_covers_each_support_setting(toolchain_config, prepared):
    config = toolchain_config('''
[backends.a]
type = "custom"
settings = { image = "tools", support = "build/support/models", klayout_support = "build/support/klayout", magic_support = "build/support/magic" }
support_profiles = { support = "models", klayout_support = "klayout", magic_support = "magic" }
[bindings]
response = "a"
''')
    created = []

    def factory(**settings):
        created.append(settings)
        return object()

    expected = {"image": "tools", "support": "build/support/models", "klayout_support": "build/support/klayout",
                "magic_support": "build/support/magic"}
    profiles = None
    if prepared:
        profiles = {name: str(config.parent / "shared cache" / name) for name in ("models", "klayout", "magic")}
        expected.update({"support": profiles["models"], "klayout_support": profiles["klayout"],
                         "magic_support": profiles["magic"]})
    original = config.read_bytes()
    declaration = load_toolchain_spec(config, require_declared=prepared)
    assert dict(declaration.backends["a"].support_profiles) == {
        "support": "models", "klayout_support": "klayout", "magic_support": "magic"}
    assert declaration.backends["a"].settings["image"] == "tools"
    load_toolchain(config, profiles=profiles, factories={"custom": factory})
    assert created == [expected]
    assert config.read_bytes() == original
    if prepared:
        del profiles["magic"]
        with pytest.raises(ValueError, match="Missing runtime profile"):
            load_toolchain(config, profiles=profiles, factories={"custom": factory})
        assert created == [expected]


@pytest.mark.parametrize("card", [
    "R1 a b model", "R1 a b 1 tc1=0.01", "R1 a b 0", "R1 a b -1",
    "R1 a b 1\n+ tc1=0.01", "R1 a b 1\nVlb_branch_R1 c 0 0",
])
def test_branch_resistors_reject_semantics_they_cannot_preserve(card):
    from benchmarking.engine.backends.ngspice import branch_resistors
    from benchmarking.files import Asset

    with pytest.raises(ValueError):
        branch_resistors(Asset((card + "\n").encode(), "spice"))


@pytest.mark.parametrize('settings', [
    {'max_parallel_jobs': 0}, {'max_parallel_jobs': True}, {'threads': 0},
    {'threads': 1.5}, {'cpu_budget': False}, {'cpu_budget': 0},
    {'max_parallel_jobs': 4, 'threads': 4, 'cpu_budget': 8},
    {'max_parallel_jobs': 1, 'threads': 9, 'cpu_budget': 16},
])
def test_ngspice_rejects_invalid_resource_allocations_before_tool_start(settings, monkeypatch):
    from benchmarking.engine.backends import ngspice

    class UnavailableTool:
        CPUS = 8

        def __init__(self, *args, **kwargs):
            pytest.fail('Invalid resource settings must not start Docker')

    monkeypatch.setattr(ngspice, 'DockerTool', UnavailableTool)
    with pytest.raises(ValueError, match='ngspice'):
        ngspice.NgspiceDocker(image='unused', **settings)


def test_ngspice_resource_settings_bind_through_toolchain_and_preserve_startup(toolchain_config, monkeypatch):
    import json

    from benchmarking.engine.backends import ngspice
    from benchmarking.engine.tools.types import ToolResult
    from benchmarking.evaluation import Job
    from benchmarking.files import Asset

    calls = []

    class Tool:
        CPUS = 8

        def __init__(self, *args):
            self.identity = {'image_id': 'test'}

        def run(self, command, files, exports, *, environment):
            calls.append((files, environment))
            return ToolResult(0, '', {'ngspice.log': Asset(b'response = 1.25\n', 'text')},
                              {'console': Asset(b'', 'text')})

    class Support:
        def mounted_files(self):
            return {'support/.spiceinit': Asset(b'echo keep-model-startup\n', 'text')}

        def evidence(self):
            return {}

    monkeypatch.setattr(ngspice, 'DockerTool', Tool)
    monkeypatch.setattr(ngspice, 'load_bundle', lambda path: Support())
    config = toolchain_config('''
[backends.simulation]
type = "ngspice-docker"
settings = {image = "test", support = "models", max_parallel_jobs = 2, threads = 4, cpu_budget = 8}
[bindings]
"circuit.simulate" = "simulation"
''')
    original = config.read_bytes()
    backend = load_toolchain(config)['circuit.simulate']
    assert backend.max_parallel_jobs == 2
    job = Job('op', 'simulate', 'circuit.simulate', (), (), (), None,
              json.dumps({'measurements': {'response': 'V'}}))
    result = backend.run(job, {'deck': Asset(b'* Control\n.control\nop\n.endc\n.end\n', 'spice')})
    assert result.status == 'passed'
    assert result.measurements['response'].value == 1.25
    files, environment = calls[0]
    assert files['support/.spiceinit'].content.startswith(b'echo keep-model-startup\n')
    assert b'set num_threads=4\n' in files['support/.spiceinit'].content
    assert environment['OMP_NUM_THREADS'] == environment['OMP_THREAD_LIMIT'] == '4'
    assert config.read_bytes() == original


# The installation adapter is a new external-I/O boundary: unlike downloaded
# resources it must never copy a PDK or expose license values in identities.
# A tiny operator-owned directory checks mutation detection and readonly binds.
def test_external_installation_binds_readonly_and_rejects_changed_identity(tmp_path, monkeypatch):
    import json

    from benchmarking.engine.external import ExternalRuntime

    installation = tmp_path / 'installed'
    installation.mkdir()
    deck = installation / 'rules'
    deck.write_text('approved deck')
    license_file = tmp_path / 'license'
    license_file.write_text('secret-license-bytes')
    profile = {'image': 'operator-image', 'environment': {'PDK_ROOT': '/pdk'},
               'pass_environment': ['CDS_LIC_FILE'], 'mounts': [
                   {'source': str(installation), 'target': '/pdk', 'release': 'v1', 'identity_paths': ['rules']},
                   {'source': str(license_file), 'target': '/license', 'release': 'operator', 'credential': True}]}
    monkeypatch.setenv('CDS_LIC_FILE', 'secret-env-value')
    runtime = ExternalRuntime('private', profile)
    args = runtime.docker_args()
    assert all(args[i+1].endswith(',readonly') for i, arg in enumerate(args) if arg == '--mount')
    assert 'secret' not in json.dumps(runtime.identity)
    assert 'secret-env-value' not in ' '.join(args)
    assert sorted(p.name for p in installation.iterdir()) == ['rules']
    deck.write_text('changed rule')
    with pytest.raises(ValueError, match='changed'):
        runtime.docker_args()
    profile['mounts'][0]['target'] = '/workspace'
    with pytest.raises(ValueError, match='mount'):
        ExternalRuntime('private', profile)
    profile['mounts'][0]['target'] = '/pdk'
    profile['mounts'][1]['source'] = str(tmp_path)
    with pytest.raises(ValueError, match='Credential mount'):
        ExternalRuntime('private', profile)


def test_external_module_selection_keeps_tool_arguments_separate(tmp_path, monkeypatch):
    """Operator module names become shell setup, never part of tool arguments."""
    from benchmarking.engine.external import ExternalRuntime

    installation = tmp_path / 'installed'
    installation.mkdir()
    (installation / 'modulefile').write_text('#%Module1.0\n')
    profile = {'image': 'operator-image', 'environment': {'MODULEPATH': '/modules'},
               'mounts': [{'source': str(installation), 'target': '/modules', 'release': 'v1',
                           'identity_paths': ['modulefile']}],
               'modules': {'pvs': ['cadence/PVS/22.20.000']}}
    runtime = ExternalRuntime('private', profile)
    command = runtime.module_command('pvs', ['pvs', '-version'])
    assert command[:2] == ['bash', '-c']
    assert 'module load cadence/PVS/22.20.000' in command[2]
    assert command[-2:] == ['pvs', '-version']

    profile['modules']['pvs'] = ['cadence/PVS/22.20.000; touch /tmp/escaped']
    with pytest.raises(ValueError, match='module'):
        ExternalRuntime('private', profile)


def test_external_pdk_subdirectories_exclude_unmounted_examples_and_symlink_escapes(tmp_path):
    from benchmarking.engine.external import ExternalRuntime

    pdk = tmp_path / 'installed'
    rules = pdk / 'rules'
    rules.mkdir(parents=True)
    (rules / 'deck').write_text('reviewed rules')
    (pdk / 'examples').mkdir()
    reference = pdk / 'examples' / 'answer'
    reference.write_text('author reference')
    runtime = ExternalRuntime('partial', {'image': 'operator-image', 'environment': {'PDK_ROOT': '/pdk'},
        'mounts': [{'source': str(rules), 'target': '/pdk/rules', 'release': '1', 'identity_paths': ['deck']}]})
    assert runtime.pdk_file('rules/deck') == (rules / 'deck', '/pdk/rules/deck')
    assert runtime.select_pdk('PDK_ROOT').environment['PDK_ROOT'] == '/pdk'
    with pytest.raises(ValueError, match='outside the declared'):
        runtime.pdk_file('examples/answer')
    (rules / 'escape').symlink_to(reference)
    with pytest.raises(ValueError, match='escapes'):
        runtime.pdk_file('rules/escape')


def test_external_pdk_file_mount_hashes_itself_and_excludes_adjacent_assets(tmp_path):
    from benchmarking.engine.external import ExternalRuntime

    deck = tmp_path / 'process.svrf'
    deck.write_text('original rule')
    (tmp_path / 'answer.gds').write_bytes(b'author reference')
    profile = {'image': 'operator', 'environment': {'PDK_ROOT': '/pdk'},
               'mounts': [{'source': str(deck), 'target': '/pdk/process.svrf',
                           'release': 'v1', 'identity_paths': [deck.name]}]}
    runtime = ExternalRuntime('files', profile)
    assert runtime.pdk_file('process.svrf') == (deck, '/pdk/process.svrf')
    with pytest.raises(ValueError, match='outside'):
        runtime.pdk_file('answer.gds')
    identity = runtime.identity
    deck.write_text('revised rule')
    assert runtime.identity != identity
    with pytest.raises(ValueError, match='changed'):
        runtime.docker_args()
    with pytest.raises(ValueError, match='basename'):
        ExternalRuntime('files', profile | {'mounts': [profile['mounts'][0] | {'identity_paths': ['answer.gds']}]})
    with pytest.raises(ValueError):
        runtime.pdk_file('rules/../examples/answer')


def test_tool_environment_only_applies_to_the_selected_tool_and_rejects_literal_license_values():
    from benchmarking.engine.external import ExternalRuntime

    profile = {'image': 'operator', 'mounts': [], 'environment': {},
               'modules': {'hspice': ['vendor/hspice'], 'customcompiler': ['vendor/customcompiler']},
               'tool_environment': {'hspice': {'LD_PRELOAD': '/lib64/libudev.so.1'}}}
    runtime = ExternalRuntime('tool-compatibility', profile)
    assert 'export LD_PRELOAD=/lib64/libudev.so.1' in runtime.module_setup('hspice')
    assert 'LD_PRELOAD' not in runtime.module_setup('customcompiler')
    assert not any('LD_PRELOAD' in arg for arg in runtime.docker_args())
    with pytest.raises(ValueError, match='license settings'):
        ExternalRuntime('literal-license', profile | {'tool_environment': {
            'hspice': {'SNPSLMD_LICENSE_FILE': '27000@server'}}})


def test_license_server_aliases_preserve_forwarded_settings_without_recording_values(monkeypatch):
    from benchmarking.engine.external import ExternalRuntime

    monkeypatch.setenv('SNPSLMD_LICENSE_FILE', '27000@local-license-alias')
    runtime = ExternalRuntime('license-transport', {'image': 'operator', 'mounts': [], 'environment': {},
        'pass_environment': ['SNPSLMD_LICENSE_FILE'], 'license_hosts': {'SNPSLMD_LICENSE_FILE': '192.0.2.1'}})
    assert 'local-license-alias=192.0.2.1' in runtime.docker_args()
    assert '27000@local-license-alias' not in str(runtime.identity)
    assert '27000@local-license-alias' not in runtime.docker_args()


def test_external_runtime_is_bound_from_process_manifest(tmp_path, monkeypatch):
    import tomli_w

    from benchmarking.engine.external import ExternalRuntime

    installation = tmp_path / 'pdk'
    installation.mkdir()
    (installation / 'rules').write_text('approved deck')
    profile = {'image': 'operator-image', 'environment': {'PDK_ROOT': '/pdk'},
               'mounts': [{'source': str(installation), 'target': '/pdk',
                           'release': 'v1', 'identity_paths': ['rules']}]}
    manifest = tmp_path / 'pdk.toml'
    manifest.write_text(tomli_w.dumps({'source': {'kind': 'external', 'runtime': 'example',
                                                  'release': 'v1'}, 'runtime': profile}))
    monkeypatch.delenv('ICLAYOUT_BENCH_EXTERNAL_CONFIG', raising=False)
    runtime = ExternalRuntime.from_manifest(manifest)
    assert runtime.name == 'example'
    assert runtime.image == 'operator-image'
    assert runtime.mounts[0]['source'] == str(installation)
