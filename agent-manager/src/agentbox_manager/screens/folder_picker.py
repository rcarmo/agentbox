from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


class FolderPickerScreen(ModalScreen[Optional[Path]]):
    """Folder picker screen for selecting workspace."""

    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def __init__(self, start_path: Optional[Path] = None):
        super().__init__()
        try:
            cwd = Path.cwd()
        except Exception:
            cwd = Path.home()
        self.start_path = start_path or cwd
        self.selected_path: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Container(id="folder-picker-dialog"):
            yield Label("📁 Select Workspace Folder", classes="dialog-title")
            yield Label(f"Starting from: {self.start_path}")
            with ScrollableContainer(id="folder-tree-container"):
                yield DirectoryTree(str(self.start_path), id="folder-tree")
            with Horizontal(id="folder-picker-buttons"):
                yield Button("Select", variant="primary", id="select-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.selected_path = Path(event.path)

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.selected_path = Path(event.path).parent

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-button" and self.selected_path:
            self.dismiss(self.selected_path)
        elif event.button.id == "cancel-button":
            self.dismiss(None)
