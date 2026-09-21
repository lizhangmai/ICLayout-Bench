import pytest

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
    from benchmarking.engine.ngspice import branch_resistors
    from benchmarking.files import Asset

    with pytest.raises(ValueError):
        branch_resistors(Asset((card + "\n").encode(), "spice"))
