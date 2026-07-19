"""CLI routing tests for the AI-first application entry point."""

from unittest.mock import patch

import pytest

from adversary_pursuit import __main__


def test_bare_ap_launches_ai_cyberdeck(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ap"])
    with patch("adversary_pursuit.agent.chat.run_chat") as run_chat:
        __main__.main()
    run_chat.assert_called_once_with()


@pytest.mark.parametrize("command", ["chat"])
def test_chat_remains_compatibility_alias(monkeypatch, command):
    monkeypatch.setattr("sys.argv", ["ap", command])
    with patch("adversary_pursuit.agent.chat.run_chat") as run_chat:
        __main__.main()
    run_chat.assert_called_once_with()


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
    assert "ap                    Launch the AI cyberdeck" in output
    assert "ap basic" in output
    assert "ap repl" in output


def test_unknown_command_fails_loudly(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ap", "unknown"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 2
    assert "Unknown command" in capsys.readouterr().err
