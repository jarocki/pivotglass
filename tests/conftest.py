"""Shared test fixtures for Adversary Pursuit."""

import sys
from pathlib import Path

import pytest

# When running tests from a git worktree, the venv's editable install points to
# the parent repo's src/ directory, not the worktree's. Prepend the worktree's
# src/ so imports resolve to the version under active development.
# This is a no-op when the worktree src is already first on sys.path.
_worktree_src = str(Path(__file__).parent.parent / "src")
if _worktree_src not in sys.path:
    sys.path.insert(0, _worktree_src)


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory for tests."""
    ws_dir = tmp_path / "workspaces"
    ws_dir.mkdir()
    return ws_dir
