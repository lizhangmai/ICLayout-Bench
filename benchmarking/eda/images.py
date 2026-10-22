"""Select a tool image without requiring a repository-specific Docker alias."""

import os

DEFAULT_IMAGE = "docker.io/lizhangmai/iclayout-bench-tools:latest"


def tool_image(image=None, *, external=None):
    """Prefer an explicit image, environment setting, declared runtime, then release."""
    return image or os.environ.get("ICLAYOUT_BENCH_IMAGE") or external or DEFAULT_IMAGE
