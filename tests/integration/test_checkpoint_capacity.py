"""Explicit capacity acceptance against the declared workspace allocation."""

import pytest
from helpers.http import checkpoint_roundtrip

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_capacity]


def test_checkpoint_near_workspace_capacity_preserves_all_bytes(host):
    service, _ = host
    checkpoint_roundtrip(host, blocks=service.controller.limits['workspace_mb'] - 4)
