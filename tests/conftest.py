"""Shared test fixtures for Adversary Pursuit."""
import pytest


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory for tests."""
    ws_dir = tmp_path / "workspaces"
    ws_dir.mkdir()
    return ws_dir
