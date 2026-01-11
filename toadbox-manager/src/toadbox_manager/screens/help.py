from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class HelpScreen(ModalScreen[None]):
    """Simple help/about dialog."""

    def compose(self) -> ComposeResult:
        help_text = (
            "🐸 Toadbox Manager\n\n"
            "c - Create new instance\n"
            "s - Start selected instance\n"
            "t - Stop selected instance\n"
            "d - Delete selected instance\n"
            "i - SSH connect to running instance\n"
            "r - RDP connect to running instance\n"
            "q - Quit"
        )
        with Container(id="help-dialog"):
            yield Label("Help", classes="dialog-title")
            yield Static(help_text, id="help-content")
            yield Button("Close", id="close-button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-button":
            self.dismiss()
