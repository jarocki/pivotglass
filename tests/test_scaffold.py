"""Smoke tests for project scaffolding."""


def test_version():
    from pivotglass import __version__
    assert __version__ == "0.9.8"


def test_main_entry_point():
    """Verify the main function exists and is callable."""
    from pivotglass.__main__ import main
    assert callable(main)


def test_subpackages_importable():
    """Verify all subpackages can be imported."""
