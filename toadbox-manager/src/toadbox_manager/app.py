from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import docker
from docker.errors import DockerException
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from toadbox_manager.models import InstanceStatus, ToadboxInstance
from toadbox_manager.screens.create_instance import CreateInstanceScreen
from toadbox_manager.screens.folder_picker import FolderPickerScreen
from toadbox_manager.screens.startup import StartupScreen
from toadbox_manager.screens.help import HelpScreen


class InstanceManagerApp(App):
    """Textual TUI application for managing Toadbox instances."""

    BINDINGS = [
        Binding("c", "create_instance", "Create"),
        Binding("s", "start_instance", "Start"),
        Binding("t", "stop_instance", "Stop"),
        Binding("d", "delete_instance", "Delete"),
        Binding("i", "connect_ssh", "SSH"),
        Binding("r", "connect_rdp", "RDP"),
        Binding("f5", "refresh", "Refresh"),
        Binding("h,?", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = (
        """
    #main-container {
        height: 100%;
        layout: grid;
        grid-size: 1 1;
    }

    #instances-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }

    #instances-table {
        height: 1fr;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        padding: 0 1;
    }

    .status-running { color: green; text-style: bold; }
    .status-stopped { color: yellow; }
    .status-error { color: red; text-style: bold; }
        """
    )

    def __init__(self) -> None:
        super().__init__()
        self.config_file = Path.home() / ".toadbox-manager.json"
        self.instances: Dict[str, ToadboxInstance] = {}
        self.docker_client: Optional[docker.DockerClient] = None
        self.load_config()
        self._init_docker_client()

    def _init_docker_client(self) -> None:
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
        except DockerException:
            self.docker_client = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="instances-panel"):
                yield Label("🐸 Toadbox Instances", classes="panel-title")
                yield DataTable(id="instances-table")
                yield Horizontal(
                    Button("Create", id="create-btn", variant="primary"),
                    Button("Start", id="start-btn"),
                    Button("Stop", id="stop-btn"),
                    Button("Delete", id="delete-btn"),
                    Button("SSH", id="ssh-btn"),
                    Button("RDP", id="rdp-btn"),
                    Button("Refresh", id="refresh-btn"),
                    Button("Help", id="help-btn"),
                    classes="button-row",
                )
                yield Static(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#instances-table", DataTable)
        table.add_columns("Name", "Status", "CPU", "Memory", "SSH", "RDP", "Priority")
        if self.docker_client:
            self.push_screen(StartupScreen(), self._handle_startup_result)
        else:
            self.refresh_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        mapping = {
            "create-btn": self.action_create_instance,
            "start-btn": self.action_start_instance,
            "stop-btn": self.action_stop_instance,
            "delete-btn": self.action_delete_instance,
            "ssh-btn": self.action_connect_ssh,
            "rdp-btn": self.action_connect_rdp,
            "refresh-btn": self.action_refresh,
            "help-btn": self.action_help,
        }
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()

    def _handle_startup_result(self, result: Optional[tuple[str, str]]) -> None:
        if not result:
            self.refresh_table()
            return
        action, value = result
        if action == "created":
            self.refresh_table()
        elif action == "connect":
            self.quick_connect(value)
        else:
            self.refresh_table()

    def load_config(self) -> None:
        if not self.config_file.exists():
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.instances = {
                name: ToadboxInstance.from_dict(payload)
                for name, payload in data.get("instances", {}).items()
            }
        except (OSError, json.JSONDecodeError):
            self.instances = {}

    def save_config(self) -> None:
        data = {"instances": {name: inst.to_dict() for name, inst in self.instances.items()}}
        with open(self.config_file, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def refresh_table(self) -> None:
        table = self.query_one("#instances-table", DataTable)
        table.clear()
        for inst in self.instances.values():
            status_style = f"status-{inst.status.value}"
            table.add_row(
                inst.name,
                f"[{status_style}]{inst.status.value}[/{status_style}]",
                str(inst.cpu_cores),
                f"{inst.memory_mb}MB",
                str(inst.ssh_port),
                str(inst.rdp_port),
                inst.priority,
                key=inst.name,
            )
        status_bar = self.query_one("#status-bar", Static)
        running = sum(1 for inst in self.instances.values() if inst.status == InstanceStatus.RUNNING)
        status_bar.update(f"Instances: {len(self.instances)} | Running: {running}")

    def get_selected_instance(self) -> Optional[ToadboxInstance]:
        table = self.query_one("#instances-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            row = table.get_row_at(table.cursor_row)
            if row:
                return self.instances.get(str(row[0]))
        except (KeyError, IndexError, LookupError, ValueError, DataTable.RowDoesNotExist):
            return None
        return None

    def action_create_instance(self) -> None:
        self.push_screen(FolderPickerScreen(), self._handle_folder_selected)

    def _handle_folder_selected(self, selected: Optional[Path]) -> None:
        if not selected:
            return
        self.push_screen(CreateInstanceScreen(selected))

    def create_instance(self, instance: ToadboxInstance) -> None:
        if instance.name in self.instances:
            self.show_error(f"Instance '{instance.name}' already exists")
            return
        self.instances[instance.name] = instance
        self.save_config()
        self.refresh_table()

    def action_start_instance(self) -> None:
        inst = self.get_selected_instance()
        if not inst:
            self.show_error("No instance selected")
            return
        if not self.docker_client:
            self.show_error("Docker is not available. Start Docker and retry.")
            return
        asyncio.create_task(self._start_async(inst))

    async def _start_async(self, instance: ToadboxInstance) -> None:
        instance.status = InstanceStatus.STARTING
        self.refresh_table()
        ok, detail = self._run_compose(instance, "up")
        if ok:
            instance.status = self._get_compose_status(instance)
            self.save_config()
        else:
            instance.status = InstanceStatus.ERROR
            message = f"Failed to start: {detail or 'no output'}"
            self.show_error(message)
        self.refresh_table()

    def action_stop_instance(self) -> None:
        inst = self.get_selected_instance()
        if not inst:
            return
        asyncio.create_task(self._stop_async(inst))

    async def _stop_async(self, instance: ToadboxInstance) -> None:
        instance.status = InstanceStatus.STOPPING
        self.refresh_table()
        ok, detail = self._run_compose(instance, "stop")
        if ok:
            instance.status = InstanceStatus.STOPPED
            self.save_config()
        else:
            instance.status = InstanceStatus.ERROR
            self.show_error(f"Failed to stop: {detail}")
        self.refresh_table()

    def action_delete_instance(self) -> None:
        inst = self.get_selected_instance()
        if not inst:
            return
        asyncio.create_task(self._delete_async(inst))

    async def _delete_async(self, instance: ToadboxInstance) -> None:
        if instance.status == InstanceStatus.RUNNING:
            await self._stop_async(instance)
        ok, detail = self._run_compose(instance, "down", include_volumes=True)
        if ok:
            self.instances.pop(instance.name, None)
            self.save_config()
        else:
            self.show_error(f"Failed to delete: {detail}")
        self.refresh_table()

    def _run_compose(self, instance: ToadboxInstance, action: str, include_volumes: bool = False) -> tuple[bool, str]:
        compose_path = self._write_compose(instance)
        env = os.environ.copy()
        env.update(
            {
                "COMPOSE_PROJECT_NAME": instance.service_name,
                "WORKSPACE_PATH": instance.workspace_folder,
                "SSH_PORT": str(instance.ssh_port),
                "RDP_PORT": str(instance.rdp_port),
                "PUID": str(instance.puid),
                "PGID": str(instance.pgid),
                "CPU_LIMITS": str(instance.cpu_cores),
                "MEMORY_LIMITS": f"{instance.memory_mb}M",
            }
        )

        docker_bin = shutil.which("docker")
        docker_compose_bin = shutil.which("docker-compose")
        compose_cmd: list[str] | None = None

        if docker_bin:
            probe = subprocess.run([docker_bin, "compose", "version"], capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                compose_cmd = [docker_bin, "compose", "-f", str(compose_path), "-p", instance.service_name, action]
        if compose_cmd is None and docker_compose_bin:
            compose_cmd = [docker_compose_bin, "-f", str(compose_path), "-p", instance.service_name, action]
        if compose_cmd is None:
            return False, "docker compose not found"
        if action == "up":
            compose_cmd.append("-d")
        if include_volumes and action == "down":
            compose_cmd.append("-v")

        result = subprocess.run(
            compose_cmd,
            cwd=compose_path.parent,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        output = (result.stderr or "").strip() or (result.stdout or "").strip()
        return result.returncode == 0, output

    def _write_compose(self, instance: ToadboxInstance) -> Path:
        if instance.compose_file:
            return Path(instance.compose_file)
        compose_dir = Path(instance.workspace_folder) / ".toadbox"
        compose_dir.mkdir(exist_ok=True)
        compose_path = compose_dir / "docker-compose.yml"
        compose_yaml = self._generate_compose(instance)
        compose_path.write_text(compose_yaml, encoding="utf-8")
        instance.compose_file = str(compose_path)
        return compose_path

    def _generate_compose(self, instance: ToadboxInstance) -> str:
        service_name = instance.service_name
        compose_dict: Dict[str, Any] = {
            "version": "3.8",
            "services": {
                service_name: {
                    "image": "toadbox",
                    "container_name": instance.hostname,
                    "hostname": instance.hostname,
                    "restart": "unless-stopped",
                    "environment": [
                        f"PUID={instance.puid}",
                        f"PGID={instance.pgid}",
                        "TERM=xterm-256color",
                        "DISPLAY=:1",
                    ],
                    "ports": [
                        f"{instance.ssh_port}:22",
                        f"{instance.rdp_port}:3389",
                    ],
                    "volumes": [
                        f"{instance.workspace_folder}:/workspace",
                        f"{service_name}_docker_data:/var/lib/docker",
                        f"{service_name}_home:/home/agent",
                    ],
                    "networks": ["toadbox_network"],
                    "privileged": True,
                    "deploy": {
                        "resources": {
                            "limits": {
                                "cpus": f"{instance.cpu_cores}",
                                "memory": f"{instance.memory_mb}M",
                            }
                        }
                    },
                }
            },
            "volumes": {
                f"{service_name}_docker_data": {"name": f"{service_name}_docker_data"},
                f"{service_name}_home": {"name": f"{service_name}_home"},
            },
            "networks": {"toadbox_network": {"driver": "bridge"}},
        }
        import yaml

        return yaml.dump(compose_dict, default_flow_style=False)

    def _get_compose_status(self, instance: ToadboxInstance) -> InstanceStatus:
        if not instance.compose_file:
            return InstanceStatus.STOPPED
        compose_path = Path(instance.compose_file)
        docker_bin = shutil.which("docker")
        docker_compose_bin = shutil.which("docker-compose")
        cmd: list[str] | None = None
        if docker_bin:
            probe = subprocess.run([docker_bin, "compose", "version"], capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                cmd = [docker_bin, "compose", "-f", str(compose_path), "-p", instance.service_name, "ps", "--services", "--filter", "status=running"]
        if cmd is None and docker_compose_bin:
            cmd = [docker_compose_bin, "-f", str(compose_path), "-p", instance.service_name, "ps", "--services", "--filter", "status=running"]
        if cmd is None:
            return InstanceStatus.ERROR
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and instance.service_name in result.stdout:
            return InstanceStatus.RUNNING
        return InstanceStatus.STOPPED

    def action_connect_ssh(self) -> None:
        inst = self.get_selected_instance()
        if not inst or inst.status != InstanceStatus.RUNNING:
            self.show_error("Select a running instance")
            return
        self._connect_ssh(inst)

    def _connect_ssh(self, instance: ToadboxInstance) -> None:
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(instance.ssh_port),
            "agent@localhost",
        ]
        self.exit()
        subprocess.run(cmd, check=False)

    def action_connect_rdp(self) -> None:
        inst = self.get_selected_instance()
        if not inst or inst.status != InstanceStatus.RUNNING:
            self.show_error("Select a running instance")
            return
        self._connect_rdp(inst)

    def _connect_rdp(self, instance: ToadboxInstance) -> None:
        rdp_commands = [
            ["xfreerdp", f"/v:localhost:{instance.rdp_port}", "/u:agent", "/p:"],
            ["open", f"rdp://localhost:{instance.rdp_port}"],
        ]
        for cmd in rdp_commands:
            try:
                self.exit()
                subprocess.run(cmd, check=False)
                return
            except FileNotFoundError:
                continue

    def action_refresh(self) -> None:
        asyncio.create_task(self._refresh_async())

    async def _refresh_async(self) -> None:
        for inst in self.instances.values():
            inst.status = self._get_compose_status(inst)
        self.save_config()
        self.refresh_table()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def show_error(self, message: str) -> None:
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(f"[red]{message}[/red]")

    def quick_connect(self, instance_name: str) -> None:
        if not self.docker_client:
            return
        containers = self.docker_client.containers.list(filters={"name": f"toadbox_{instance_name}"})
        if not containers:
            return
        container = containers[0]
        ports = container.ports or {}
        ssh_host_port = ports.get("22/tcp", [{}])[0].get("HostPort", "2222")
        rdp_host_port = ports.get("3389/tcp", [{}])[0].get("HostPort", "3390")
        inst = ToadboxInstance(
            name=instance_name,
            workspace_folder="",
            ssh_port=int(ssh_host_port),
            rdp_port=int(rdp_host_port),
            status=InstanceStatus.RUNNING,
        )
        self._connect_ssh(inst)


def main() -> None:
    app = InstanceManagerApp()
    app.run()


__all__ = ["InstanceManagerApp", "main"]
