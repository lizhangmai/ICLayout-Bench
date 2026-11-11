"""Select a tool image without requiring a repository-specific Docker alias."""

import os
import re
from importlib.metadata import PackageNotFoundError, version

REPOSITORY = "docker.io/lizhangmai/iclayout-bench-tools"
# Public releases (no development or local segment) publish a matching v<version> image.
_RELEASE = re.compile(r"\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?")


def release_image(package_version):
    """Return the image published with a release; development builds follow latest."""
    if package_version and _RELEASE.fullmatch(package_version):
        return f"{REPOSITORY}:v{package_version}"
    return f"{REPOSITORY}:latest"


def _installed_version():
    try:
        return version("iclayout-bench")
    except PackageNotFoundError:
        return None


DEFAULT_IMAGE = release_image(_installed_version())


def tool_image(image=None, *, external=None):
    """Prefer an explicit image, environment setting, declared runtime, then release."""
    return image or os.environ.get("ICLAYOUT_BENCH_IMAGE") or external or DEFAULT_IMAGE
