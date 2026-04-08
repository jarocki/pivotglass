"""Spike: verify cmd2 + Rich integration works."""
import cmd2
from rich.console import Console
from rich.table import Table
import io


def test_rich_renders_inside_cmd2():
    """Verify Rich output can render within a cmd2 command handler."""
    class TestApp(cmd2.Cmd):
        def __init__(self):
            super().__init__()
            self.rich_console = Console(file=io.StringIO())

        def do_test(self, _):
            table = Table(title="Test")
            table.add_column("Key")
            table.add_column("Value")
            table.add_row("hello", "world")
            self.rich_console.print(table)

    app = TestApp()
    app.onecmd_plus_hooks("test")
    output = app.rich_console.file.getvalue()
    assert "hello" in output
    assert "world" in output


def test_cmd2_has_rich_support():
    """Check if cmd2 has native Rich console classes."""
    has_native = hasattr(cmd2, 'Cmd2BaseConsole')
    print(f"cmd2 native Rich support: {has_native}")
    # This test always passes - it's a discovery spike
