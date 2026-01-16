from __future__ import annotations

from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from agentbox_manager.screens.create_instance import CreateInstanceScreen
from agentbox_manager.screens.folder_picker import FolderPickerScreen


class StartupScreen(ModalScreen[Optional[tuple[str, str]]]):
    """Startup dialog listing running instances."""

    BINDINGS = [
        Binding("escape,q", "quit", "Quit"),
        Binding("c", "create_new", "Create"),
        Binding("enter", "connect", "Connect"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="startup-container"):
            yield Static("🐸 Agent Manager", id="title")
            yield Static(
                "Select a running instance or create a new one.", id="subtitle"
            )
            yield DataTable(id="running-instances-table")
            with Horizontal(id="button-container"):
                yield Button("Create New Instance", id="create-btn", variant="primary")
                yield Button("Refresh", id="refresh-btn")
                yield Button("Quit", id="quit-btn", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#running-instances-table", DataTable)
        table.add_columns("Name", "Status", "SSH Port", "RDP Port", "Action")
        self.refresh_instances()

    def refresh_instances(self) -> None:
        table = self.query_one("#running-instances-table", DataTable)
        table.clear()
        running_instances = []
        try:
            docker_client = docker.from_env()
            containers = docker_client.containers.list(
                all=True, filters={"name": "agentbox"}
            )
            for container in containers:
                container_name = container.name or "unknown"
                name = container_name.replace("agentbox_", "").replace("agentbox-", "")
                status = "Running" if container.status == "running" else "Stopped"
                ports = container.ports or {}
                ssh_port = ports.get("22/tcp", [{}])[0].get("HostPort", "N/A")
                rdp_port = ports.get("3389/tcp", [{}])[0].get("HostPort", "N/A")
                action = "Connect" if container.status == "running" else "Start"
                if container.status == "running":
                    table.add_row(name, status, ssh_port, rdp_port, action, key=name)
                    running_instances.append(name)
        except DockerException as exc:
            table.add_row("Error", f"Failed to load: {exc}", "-", "-", "-", key="error")
        subtitle = self.query_one("#subtitle", Static)
        if running_instances:
            subtitle.update(f"Found {len(running_instances)} running instance(s).")
        else:
            subtitle.update("No running instances found. Create one to get started.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-btn":
            self.action_create_new()
        elif event.button.id == "refresh-btn":
            self.refresh_instances()
        elif event.button.id == "quit-btn":
            self.action_quit()

    def action_create_new(self) -> None:
        self.app.push_screen(FolderPickerScreen(), self._handle_folder_for_create)

    def _handle_folder_for_create(self, selected_path: Optional[Path]) -> None:
        if selected_path:
            self.app.push_screen(
                CreateInstanceScreen(selected_path), self._handle_create_result
            )
        else:
            self.dismiss(None)

    def _handle_create_result(self, result: Optional[str]) -> None:
        if result:
            self.dismiss(("created", result))
        else:
            self.dismiss(None)

    def action_connect(self) -> None:
        table = self.query_one("#running-instances-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is None:
            return
        try:
            row_key = table.get_row_key(cursor_row)
        except (KeyError, IndexError, LookupError):
            return
        if row_key and row_key not in ["error", "nodocker"]:
            self.dismiss(("connect", row_key))

    def action_quit(self) -> None:
        self.dismiss(None)
