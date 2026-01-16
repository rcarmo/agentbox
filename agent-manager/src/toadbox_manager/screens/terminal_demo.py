from __future__ import annotations

from textual.screen import Screen
from textual.widgets import Static
from toadbox_manager.screens.terminal_widget import TerminalWidget


class TerminalDemoScreen(Screen):
    def compose(self):
        yield Static("Embedded Terminal Demo - press q to quit")
        yield TerminalWidget(cmd=["/bin/bash"], cols=100, rows=30)

    def on_key(self, event):
        if event.key == "q":
            self.app.pop_screen()
