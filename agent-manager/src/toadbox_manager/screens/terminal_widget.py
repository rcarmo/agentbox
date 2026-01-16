from __future__ import annotations

import asyncio
import os
import subprocess
import fcntl
import termios
import pyte
from typing import Optional

from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive


class TerminalClosed(Message):
    pass


class TerminalWidget(Widget):
    """A very small terminal emulator widget using pyte and a PTY.

    This is minimal: it reads from a PTY, feeds bytes to `pyte.Stream`, and
    renders the screen content as plain text. It forwards keyboard bytes to
    the PTY master. It does not implement mouse support or full VT100 features.
    """

    process_pid: Optional[int] = None
    master_fd: Optional[int] = None
    cols: int = 80
    rows: int = 24
    screen = reactive("")

    def __init__(self, cmd: list[str] = ["/bin/bash"], *, cols: int = 80, rows: int = 24) -> None:
        super().__init__()
        self.cmd = cmd
        self.cols = cols
        self.rows = rows
        self.py_screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.Stream(self.py_screen)

    async def on_mount(self) -> None:
        # Open a pty and spawn the process
        self.master_fd, slave_fd = os.openpty()
        # set non-blocking
        fl = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self.proc = subprocess.Popen(self.cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
        self.process_pid = self.proc.pid
        os.close(slave_fd)
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, self.master_fd, 4096)
            except Exception:
                data = b""
            if not data:
                break
            try:
                self.stream.feed(data.decode("utf-8", "replace"))
            except Exception:
                pass
            # Update screen text from pyte buffer
            text = "\n".join(self.py_screen.display)
            self.screen = text
            self.refresh()
        await self.emit(TerminalClosed())

    def render(self) -> str:
        return self.screen

    async def key_press(self, event) -> None:  # placeholder for Textual key events
        if not self.master_fd:
            return
        data = event.key.encode("utf-8")
        try:
            os.write(self.master_fd, data)
        except Exception:
            pass
