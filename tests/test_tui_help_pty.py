"""Real-terminal help navigation and input isolation, without integrations."""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX PTY required")
@pytest.mark.parametrize("columns,rows", [(80, 24), (120, 40)])
def test_help_fits_terminal_scrolls_and_restores_input(columns, rows):
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    report_read, report_write = os.pipe()
    child = r'''
import asyncio, json, os, sys
from prompt_toolkit.history import InMemoryHistory
from pivotglass.agent.tui.application import TuiApplication
from pivotglass.agent.tui.events import EventBus

class IsolatedTui(TuiApplication):
    @staticmethod
    def _build_history():
        return InMemoryHistory()

tui = IsolatedTui(None, None, None, EventBus())
for number in range(100):
    tui._scrollback.emit_line(f"history {number}")
tui._scroll_offset = 9
fd = int(sys.argv[1])
def capture():
    screen = tui._app.renderer._last_screen
    text = "\n".join("".join(row[x].char for x in range(tui._app.output.get_size().columns))
                     for _, row in sorted(screen.data_buffer.items()))
    report = dict(text=text, help=tui._help_visible, cursor=tui._help_cursor,
                  history=tui._scroll_offset, input=tui._input_buffer.text,
                  input_focused=tui._app.layout.has_focus(tui._input_buffer))
    os.write(fd, (json.dumps(report) + "\n").encode())
@tui._app.key_bindings.add("f12")
def snapshot(event):
    async def later():
        await asyncio.sleep(.1)
        capture()
    event.app.create_background_task(later())
async def ready():
    await asyncio.sleep(.1)
    capture()
tui._app.run(pre_run=lambda: tui._app.create_background_task(ready()))
tui._executor.shutdown(wait=True)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", child, str(report_write)],
        stdin=slave, stdout=slave, stderr=slave,
        pass_fds=(report_write,),
        env={**os.environ, "TERM": "xterm-256color", "PROMPT_TOOLKIT_NO_CPR": "1"},
    )
    os.close(slave)
    os.close(report_write)
    pending = b""

    def receipt(keys=None):
        nonlocal pending
        import time

        if keys is not None:
            os.write(master, keys + b"\x1b[24~")  # F12 records actual rendered frame.
        deadline = time.monotonic() + 10
        while b"\n" not in pending:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "TUI did not produce a rendered-frame receipt"
            ready, _, _ = select.select([master, report_read], [], [], remaining)
            if master in ready:
                os.read(master, 65536)  # Drain terminal output so rendering cannot block.
            if report_read in ready:
                data = os.read(report_read, 65536)
                assert data, "TUI exited before the requested frame"
                pending += data
        line, pending = pending.split(b"\n", 1)
        return json.loads(line)

    try:
        receipt()
        opened = receipt(b"?")
        assert opened["help"]
        assert "QUICK CONTROL" in opened["text"]
        assert "Esc: close" in opened["text"]
        assert not opened["input_focused"]
        tabbed = receipt(b"\t")
        assert not tabbed["input_focused"]
        paged = receipt(b"\x1b[6~")
        assert paged["cursor"] > 0
        paged_back = receipt(b"\x1b[5~")
        assert paged_back["cursor"] < paged["cursor"]
        end = receipt(b"\x1b[F")
        assert "Press Esc" in end["text"]
        assert "Esc: close" in end["text"]
        ignored = receipt(b"accidental typing")
        assert ignored["input"] == ""
        assert ignored["history"] == 9
        top = receipt(b"\x1b[H")
        assert top["cursor"] == 0
        arrow = receipt(b"\x1b[B")
        assert arrow["cursor"] == 1
        assert arrow["history"] == 9
        arrow_up = receipt(b"\x1b[A")
        assert arrow_up["cursor"] == 0
        assert arrow_up["history"] == 9
        # Mouse scrolling over help must never move investigation history.
        wheeled = receipt(f"\x1b[<65;{columns // 2};{rows // 2}M".encode())
        assert wheeled["history"] == 9
        assert wheeled["cursor"] > arrow["cursor"]
        closed = receipt(b"\x1b")
        assert not closed["help"]
        assert closed["input_focused"]
        typed = receipt(b"question?")
        assert typed["input"] == "question?"
        assert not typed["help"]
    finally:
        if process.poll() is None:
            os.write(master, b"\x03")
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
        os.close(master)
        os.close(report_read)
