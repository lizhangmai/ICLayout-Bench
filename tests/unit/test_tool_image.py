"""Released packages default to the tools image published with them."""

import subprocess
import sys

import pytest

from benchmarking.eda import images

pytestmark = pytest.mark.unit

REPOSITORY = "docker.io/lizhangmai/iclayout-bench-tools"


@pytest.mark.parametrize("version,expected", [
    ("0.8.1", f"{REPOSITORY}:v0.8.1"),
    ("1.0.0rc1", f"{REPOSITORY}:v1.0.0rc1"),
    ("1.0.0.post2", f"{REPOSITORY}:v1.0.0.post2"),
    ("0.8.2.dev4+g94c74ad61.d20261111", f"{REPOSITORY}:latest"),
    ("1.0.0+local", f"{REPOSITORY}:latest"),
    (None, f"{REPOSITORY}:latest"),
])
def test_release_versions_select_their_published_image(version, expected):
    assert images.release_image(version) == expected


def test_explicit_and_environment_images_override_the_release_default(monkeypatch):
    monkeypatch.setenv("ICLAYOUT_BENCH_IMAGE", "registry.example/eda:reviewed")
    assert images.tool_image() == "registry.example/eda:reviewed"
    assert images.tool_image("selected-image") == "selected-image"
    monkeypatch.delenv("ICLAYOUT_BENCH_IMAGE")
    assert images.tool_image(external="registry.example/vendor:1") == "registry.example/vendor:1"
    assert images.tool_image() == images.DEFAULT_IMAGE


def test_eda_image_command_prints_the_selected_image(monkeypatch):
    monkeypatch.setenv("ICLAYOUT_BENCH_IMAGE", "registry.example/eda:reviewed")
    output = subprocess.run([sys.executable, "-m", "benchmarking.eda", "image"],
                            check=True, capture_output=True, text=True).stdout
    assert output == "registry.example/eda:reviewed\n"
