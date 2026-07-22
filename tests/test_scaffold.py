"""Smoke tests for project scaffolding."""


def test_version():
    from adversary_pursuit import __version__
    assert __version__ == "0.4.9"


def test_main_entry_point():
    """Verify the main function exists and is callable."""
    from adversary_pursuit.__main__ import main
    assert callable(main)


def test_subpackages_importable():
    """Verify all subpackages can be imported."""
