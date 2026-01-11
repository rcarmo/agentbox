from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from toadbox_manager.models import ToadboxInstance


class CreateInstanceScreen(ModalScreen[Optional[ToadboxInstance]]):
    """Modal screen for creating new instances."""

    DEFAULT_CSS = """
    #create-dialog {
        width: 100%;
        height: 100%;
        layout: vertical;
        padding: 1 2;
        background: $surface;
        border: heavy $primary;
    }

    #create-form {
        height: 1fr;
        layout: vertical;
        row-gap: 1;
        overflow: auto;
    }

    #name-browse-row {
        width: 100%;
        layout: horizontal;
        column-gap: 1;
        align: left middle;
    }

    #name-input {
        width: 1fr;
        min-width: 30;
    }

    #workspace-label {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    Input, Select {
        width: 100%;
    }

    .button-row {
        width: 100%;
        align: right middle;
        column-gap: 1;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Close"),
        ("tab", "focus_next", "Next field"),
        ("shift+tab", "focus_previous", "Previous field"),
    ]

    def __init__(self, workspace_folder: Optional[Path] = None):
        super().__init__()
        self.workspace_folder = workspace_folder

    def compose(self) -> ComposeResult:
        with Container(id="create-dialog"):
            yield Label("Create New Toadbox Instance", classes="dialog-title")

            with ScrollableContainer(id="create-form"):
                yield Label("Instance Name / Workspace:")
                with Horizontal(id="name-browse-row"):
                    name_input = Input(placeholder="my-toadbox", id="name-input")
                    if self.workspace_folder:
                        name_input.value = self.workspace_folder.name
                    yield name_input
                    yield Button("Browse", variant="default", id="browse-button")

                yield Label("Workspace Folder:")
                yield Label(str(self.workspace_folder or "No folder selected"), id="workspace-label")

                yield Label("CPU Cores:")
                yield Select([(str(i), str(i)) for i in range(1, 9)], value="2", id="cpu-select")

                yield Label("Memory (MB):")
                yield Select(
                    [("2048", "2048"), ("4096", "4096"), ("8192", "8192"), ("16384", "16384")],
                    value="4096",
                    id="memory-select",
                )

                yield Label("Priority:")
                yield Select(
                    [("low", "low"), ("medium", "medium"), ("high", "high")],
                    value="low",
                    id="priority-select",
                )

                yield Label("SSH Port:")
                yield Input(placeholder="2222", value="2222", id="ssh-port-input")

                yield Label("RDP Port:")
                yield Input(placeholder="3390", value="3390", id="rdp-port-input")

                try:
                    current_user = pwd.getpwuid(os.getuid())
                    default_puid = str(current_user.pw_uid)
                    default_pgid = str(current_user.pw_gid)
                except OSError:
                    default_puid = "1000"
                    default_pgid = "1000"

                yield Label("User ID (PUID):")
                yield Input(placeholder=default_puid, value=default_puid, id="puid-input")

                yield Label("Group ID (PGID):")
                yield Input(placeholder=default_pgid, value=default_pgid, id="pgid-input")

            with Horizontal(classes="button-row"):
                yield Button("Create", variant="primary", id="create-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self) -> None:
        self.query_one("#create-form", ScrollableContainer).focus()
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-button":
            self._create_instance()
        elif event.button.id == "cancel-button":
            self.app.pop_screen()
        elif event.button.id == "browse-button":
            from toadbox_manager.screens.folder_picker import FolderPickerScreen

            self.app.push_screen(FolderPickerScreen(), self.handle_folder_selection)

    def _create_instance(self) -> None:
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            name = self.workspace_folder.name if self.workspace_folder else "toadbox"

        cpu_select = self.query_one("#cpu-select", Select)
        try:
            cpu_cores = int(cpu_select.value) if cpu_select.value else 2
        except (ValueError, TypeError):
            cpu_cores = 2

        memory_select = self.query_one("#memory-select", Select)
        try:
            memory_value = memory_select.value if memory_select.value else "4096"
            memory_mb = int(memory_value)
        except (ValueError, TypeError, AttributeError):
            memory_mb = 4096

        priority_value = str(self.query_one("#priority-select", Select).value or "low")
        priority = priority_value

        ssh_port = int(self.query_one("#ssh-port-input", Input).value or "2222")
        rdp_port = int(self.query_one("#rdp-port-input", Input).value or "3390")
        puid = int(self.query_one("#puid-input", Input).value or "1000")
        pgid = int(self.query_one("#pgid-input", Input).value or "1000")

        instance = ToadboxInstance(
            name=name,
            workspace_folder=str(self.workspace_folder or Path.cwd()),
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            priority=priority,
            ssh_port=ssh_port,
            rdp_port=rdp_port,
            puid=puid,
            pgid=pgid,
        )

        app_manager = self.app
        if hasattr(app_manager, "create_instance"):
            app_manager.create_instance(instance)
        self.app.pop_screen()

    def handle_folder_selection(self, selected_path: Optional[Path]) -> None:
        if selected_path:
            self.workspace_folder = selected_path
            self.query_one("#workspace-label", Label).update(str(selected_path))
            name_input = self.query_one("#name-input", Input)
            if not name_input.value:
                name_input.value = selected_path.name
