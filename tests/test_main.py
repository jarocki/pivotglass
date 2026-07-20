"""CLI routing tests for the AI-first application entry point."""

from unittest.mock import patch

import pytest

from adversary_pursuit import __main__


def test_bare_ap_launches_web_cockpit(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ap"])
    with patch("adversary_pursuit.web.server.run_web") as run_web:
        __main__.main()
    run_web.assert_called_once_with()


@pytest.mark.parametrize("command", ["chat", "tui"])
def test_terminal_cyberdeck_aliases(monkeypatch, command):
    monkeypatch.setattr("sys.argv", ["ap", command])
    with patch("adversary_pursuit.agent.chat.run_chat") as run_chat:
        __main__.main()
    run_chat.assert_called_once_with()


def test_web_command_launches_web_cockpit(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ap", "web"])
    with patch("adversary_pursuit.web.server.run_web") as run_web:
        __main__.main()
    run_web.assert_called_once_with()


@pytest.mark.parametrize("command", ["basic", "repl"])
def test_basic_aliases_launch_classic_console(monkeypatch, command):
    monkeypatch.setattr("sys.argv", ["ap", command])
    with patch.object(__main__, "_run_basic") as run_basic:
        __main__.main()
    run_basic.assert_called_once_with()


def test_help_describes_both_interfaces(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ap", "--help"])
    __main__.main()
    output = capsys.readouterr().out
    assert "ap                    Launch the local Pivotglass web cockpit" in output
    assert "ap tui" in output
    assert "ap basic" in output
    assert "ap repl" in output


def test_unknown_command_fails_loudly(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ap", "unknown"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 2
    assert "Unknown command" in capsys.readouterr().err
