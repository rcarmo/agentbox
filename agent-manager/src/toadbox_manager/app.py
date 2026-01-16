from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import docker
import yaml
from docker.errors import DockerException
import time
import pty
from toadbox_manager import terminal
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from toadbox_manager.models import InstanceStatus, ToadboxInstance
from toadbox_manager.screens.create_instance import CreateInstanceScreen
from toadbox_manager.screens.folder_picker import FolderPickerScreen
from toadbox_manager.screens.startup import StartupScreen
from toadbox_manager.screens.help import HelpScreen
from toadbox_manager.screens.terminal_demo import TerminalDemoScreen


class InstanceManagerApp(App):
    """Textual TUI application for managing Toadbox instances."""

    BINDINGS = [
        Binding("c", "create_instance", "Create"),
        Binding("a", "attach", "Attach"),
        Binding("s", "start_instance", "Start"),
        Binding("t", "stop_instance", "Stop"),
        Binding("d", "delete_instance", "Delete"),
        Binding("i", "connect_ssh", "SSH"),
        Binding("r", "connect_rdp", "RDP"),
        Binding("f5", "refresh", "Refresh"),
        Binding("h,?", "help", "Help"),
        Binding("T", "terminal_demo", "Terminal Demo"),
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

    .button-row {
        layout: horizontal;
        width: 100%;
    }

    .button-row Button {
        width: auto;
        min-width: 8;
        padding: 0 1;
        margin-right: 1;
    }

    .status-running { color: green; text-style: bold; }
    .status-stopped { color: yellow; }
    .status-error { color: red; text-style: bold; }
        """
    )
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Initialize core state used across the app and tests.
        super().__init__(*args, **kwargs)
        # Instances registry: name -> ToadboxInstance
        self.instances: Dict[str, ToadboxInstance] = {}
        # Compose / config paths under the user's home by default
        self.compose_dir: Path = Path.home() / ".toadbox-manager"
        self.compose_path: Path = self.compose_dir / "docker-compose.yml"
        self.compose_project: str = "toadbox"
        self.config_file: Path = self.compose_dir / "config.json"
        # Try to initialize Docker SDK client but fall back gracefully
        try:
            self.docker_client = docker.from_env()
        except DockerException:
            self.docker_client = None
        except Exception:
            self.docker_client = None
        # Detect whether docker or docker-compose CLI is available
        self.docker_cli_available = bool(shutil.which("docker") or shutil.which("docker-compose"))
    def _init_docker_client(self) -> None:
        """Initialize or reinitialize the Docker SDK client and CLI availability flag.

        This is called before actions that need Docker to ensure the app has
        up-to-date knowledge about SDK/CLI availability.
        """
        try:
            self.docker_client = docker.from_env()
        except DockerException:
            self.docker_client = None
        except Exception:
            self.docker_client = None

        # Refresh CLI availability
        self.docker_cli_available = bool(shutil.which("docker") or shutil.which("docker-compose"))

        # Ensure compose/config attributes exist
        if not getattr(self, "compose_dir", None):
            self.compose_dir = Path.home() / ".toadbox-manager"
        if not getattr(self, "compose_path", None):
            self.compose_path = self.compose_dir / "docker-compose.yml"
        if not getattr(self, "compose_project", None):
            self.compose_project = "toadbox"
        if not getattr(self, "config_file", None):
            self.config_file = self.compose_dir / "config.json"
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="main-container"):
            with Vertical(id="instances-panel"):
                yield Label("🐸 Toadbox Instances", classes="panel-title")
                yield DataTable(id="instances-table")
                yield Horizontal(
                    Button("Create", id="create-btn", variant="primary"),
                    Button("Start", id="start-btn"),
                    Button("Stop", id="stop-btn"),
                    Button("Delete", id="delete-btn"),
                    Button("Attach", id="attach-btn"),
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
        # If the demo env var is set, open the embedded terminal demo
        if os.environ.get("TOADBOX_TERMINAL_DEMO"):
            self.push_screen(TerminalDemoScreen())
            return
        if self.docker_client:
            self.push_screen(StartupScreen(), self._handle_startup_result)
        else:
            self.refresh_table()

    def action_terminal_demo(self) -> None:
        self.push_screen(TerminalDemoScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        mapping = {
            "create-btn": self.action_create_instance,
            "attach-btn": self.action_attach_instance,
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
        # Keep the unified compose file in sync with saved instances
        self._write_compose()

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
            # DataTable implementations may vary; guard against any lookup errors
            if table.row_count == 0:
                return None
            row = table.get_row_at(table.cursor_row)
            if not row:
                return None
            return self.instances.get(str(row[0]))
        except (KeyError, IndexError, LookupError, ValueError, AttributeError):
            return None
        return None

    def action_create_instance(self) -> None:
        self.push_screen(FolderPickerScreen(), self._handle_folder_selected)

    def _handle_folder_selected(self, selected: Optional[Path]) -> None:
        if not selected:
            return
        self.push_screen(CreateInstanceScreen(selected))

    def create_instance(self, instance: ToadboxInstance) -> None:
        for existing_name, existing in self.instances.items():
            conflicts = []
            if existing.ssh_port == instance.ssh_port:
                conflicts.append("SSH")
            if existing.rdp_port == instance.rdp_port:
                conflicts.append("RDP")
            if conflicts:
                ports = ", ".join(conflicts)
                self.show_error(f"Ports already in use by '{existing_name}' ({ports})")
                return
        if instance.name in self.instances:
            self.show_error(f"Instance '{instance.name}' already exists")
            return
        self.instances[instance.name] = instance
        self.save_config()
        self.refresh_table()

    def suggest_ports(self, ssh_start: int = 2222, rdp_start: int = 3390) -> tuple[int, int]:
        """Return the next available (ssh_port, rdp_port) not used by existing instances."""
        used_ssh = {inst.ssh_port for inst in self.instances.values()}
        used_rdp = {inst.rdp_port for inst in self.instances.values()}

        ssh_port = ssh_start
        while ssh_port in used_ssh:
            ssh_port += 1

        rdp_port = rdp_start
        while rdp_port in used_rdp:
            rdp_port += 1

        return ssh_port, rdp_port

    def action_start_instance(self) -> None:
        # Reinitialize docker client in case Docker became available after app start
        self._init_docker_client()
        inst = self.get_selected_instance()
        if not inst:
            self.show_error("No instance selected")
            return
        if not self.docker_client and not getattr(self, "docker_cli_available", False):
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
        ok, detail = self._run_compose(instance, "rm", include_volumes=True)
        if ok:
            self.instances.pop(instance.name, None)
            self.save_config()
        else:
            self.show_error(f"Failed to delete: {detail}")
        self.refresh_table()

    def _build_compose_spec(self) -> Dict[str, Any]:
        services: Dict[str, Any] = {}
        volumes: Dict[str, Any] = {}

        for inst in self.instances.values():
            service_name = inst.service_name
            services[service_name] = {
                "image": "toadbox",
                "container_name": inst.hostname,
                "hostname": inst.hostname,
                "restart": "unless-stopped",
                "environment": [
                    f"PUID={inst.puid}",
                    f"PGID={inst.pgid}",
                    "TERM=xterm-256color",
                    "DISPLAY=:1",
                ],
                "ports": [
                    f"{inst.ssh_port}:22",
                    f"{inst.rdp_port}:3389",
                ],
                "volumes": [
                    f"{inst.workspace_folder}:/workspace",
                    f"{service_name}_docker_data:/var/lib/docker",
                    f"{service_name}_home:/home/agent",
                ],
                "networks": ["toadbox_network"],
                "privileged": True,
                "deploy": {
                    "resources": {
                        "limits": {
                            "cpus": f"{inst.cpu_cores}",
                            "memory": f"{inst.memory_mb}M",
                        }
                    }
                },
            }

            volumes[f"{service_name}_docker_data"] = {"name": f"{service_name}_docker_data"}
            volumes[f"{service_name}_home"] = {"name": f"{service_name}_home"}

        compose_dict: Dict[str, Any] = {
            "version": "3.8",
            "services": services,
            "volumes": volumes,
            "networks": {"toadbox_network": {"driver": "bridge"}},
        }
        return compose_dict

    def _write_compose(self) -> Path:
        """Write a single docker-compose file containing all instances."""
        self.compose_dir.mkdir(exist_ok=True)
        compose_dict = self._build_compose_spec()
        self.compose_path.write_text(yaml.dump(compose_dict, default_flow_style=False), encoding="utf-8")
        return self.compose_path

    def _run_compose(self, instance: ToadboxInstance, action: str, include_volumes: bool = False) -> tuple[bool, str]:
        compose_path = self._write_compose()
        docker_bin = shutil.which("docker")
        docker_compose_bin = shutil.which("docker-compose")
        base_cmd: list[str] | None = None

        if docker_bin:
            probe = subprocess.run([docker_bin, "compose", "version"], capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                base_cmd = [docker_bin, "compose", "-f", str(compose_path), "-p", self.compose_project]
        if base_cmd is None and docker_compose_bin:
            base_cmd = [docker_compose_bin, "-f", str(compose_path), "-p", self.compose_project]
        if base_cmd is None:
            return False, "docker compose not found"

        if action == "up":
            cmd = base_cmd + ["up", "-d", instance.service_name]
        elif action == "stop":
            cmd = base_cmd + ["stop", instance.service_name]
        elif action == "rm":
            cmd = base_cmd + ["rm", "-s", "-f"]
            if include_volumes:
                cmd.append("-v")
            cmd.append(instance.service_name)
        else:
            cmd = base_cmd + [action, instance.service_name]

        result = subprocess.run(
            cmd,
            cwd=self.compose_path.parent,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            check=False,
        )
        output = (result.stderr or "").strip() or (result.stdout or "").strip()
        return result.returncode == 0, output

    def _get_compose_status(self, instance: ToadboxInstance) -> InstanceStatus:
        if not self.compose_path.exists():
            return InstanceStatus.STOPPED
        docker_bin = shutil.which("docker")
        docker_compose_bin = shutil.which("docker-compose")
        base_cmd: list[str] | None = None
        if docker_bin:
            probe = subprocess.run([docker_bin, "compose", "version"], capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                base_cmd = [docker_bin, "compose", "-f", str(self.compose_path), "-p", self.compose_project]
        if base_cmd is None and docker_compose_bin:
            base_cmd = [docker_compose_bin, "-f", str(self.compose_path), "-p", self.compose_project]
        if base_cmd is None:
            return InstanceStatus.ERROR

        cmd = base_cmd + ["ps", "--services", "--filter", "status=running", instance.service_name]
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

    def action_attach_instance(self) -> None:
        # Re-check Docker availability before attempting to attach
        self._init_docker_client()
        inst = self.get_selected_instance()
        if not inst or inst.status != InstanceStatus.RUNNING:
            self.show_error("Select a running instance")
            return
        self._attach_to_container(inst)

    def _attach_to_container(self, instance: ToadboxInstance) -> None:
        # Attempt to attach to the running container and open a tmux session
        # Use docker exec to run tmux inside the container
        # If SDK client available, prefer it
        _run_restore = terminal.restore_terminal

        if self.docker_client:
            try:
                containers = self.docker_client.containers.list(filters={"name": instance.service_name})
            except Exception:
                containers = []

            if not containers:
                self.show_error("Container not found")
                return

            container = containers[0]
            target = container.name if hasattr(container, "name") else container.id

            cmd = ["docker", "exec", "-it", "--user", "agent", target, "tmux", "new", "-As0"]
            # Inform user we're attempting attach
            try:
                status_bar = self.query_one("#status-bar", Static)
                status_bar.update(f"Attaching to {instance.name}...")
            except Exception:
                pass
            # Prefer PTY spawn for interactive tty behavior, fall back to execvp or subprocess
            try:
                self.exit()
                # Allow Textual to teardown terminal; tuned longer for reliability
                time.sleep(1.5)
                # use terminal helper which handles run/pty/execvp + restore
                ok = terminal.attach_command(cmd, delay=1.5)
                try:
                    status_bar.update("")
                except Exception:
                    pass
                if ok:
                    return
                self.show_error("Failed to attach to container")
                return
            except Exception:
                self.show_error("Failed to attach to container")
                return

        # Fallback to Docker CLI if available
        if getattr(self, "docker_cli_available", False):
            try:
                # Find a container name matching the service
                probe = subprocess.run(
                    ["docker", "ps", "--filter", f"name={instance.service_name}", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                names = [n for n in (probe.stdout or "").splitlines() if n.strip()]
                if not names:
                    self.show_error("Container not found")
                    return
                target = names[0]
                cmd = ["docker", "exec", "-it", "--user", "agent", target, "tmux", "new", "-As0"]
                self.exit()
                try:
                    status_bar = self.query_one("#status-bar", Static)
                    status_bar.update(f"Attaching to {instance.name}...")
                except Exception:
                    pass
                ok = terminal.attach_command(cmd, delay=1.5)
                try:
                    status_bar.update("")
                except Exception:
                    pass
                if ok:
                    return
                return
            except Exception:
                self.show_error("Failed to attach to container")
                return

        # If we reach here, neither SDK nor CLI are available
        self.show_error("Docker is not available. Start Docker and retry.")

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
        self._write_compose()
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
