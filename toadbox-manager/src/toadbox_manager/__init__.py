"""Toadbox Manager - TUI for managing multiple toadbox instances."""

import asyncio
import json
import os
import pwd
import signal
import shutil
import subprocess
import sys
import time
import yaml
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import docker
from docker.errors import DockerException
from rich.console import Console
from rich.table import Table
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, Select, Switch, Static, DirectoryTree
)


class InstanceStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ToadboxInstance:
    name: str
    workspace_folder: str
    cpu_cores: int = 2
    memory_mb: int = 4096
    priority: str = "low"
    ssh_port: int = 2222
    vnc_port: int = 5901
    puid: int = 1000
    pgid: int = 1000
    status: InstanceStatus = InstanceStatus.STOPPED
    compose_file: Optional[str] = None
    container_id: Optional[str] = None
    
    @property
    def service_name(self) -> str:
        """Generate docker-compose service name based on folder."""
        return Path(self.workspace_folder).name.replace('-', '_').lower()
    
    @property
    def hostname(self) -> str:
        """Generate hostname based on folder."""
        folder_name = Path(self.workspace_folder).name
        return f"toadbox-{folder_name}"
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ToadboxInstance':
        # Backwards/forwards compatibility with older config versions.
        data = dict(data)
        if 'status' in data:
            data['status'] = InstanceStatus(data['status'])
        else:
            data['status'] = InstanceStatus.STOPPED

        # These are computed properties, not dataclass fields.
        data.pop('service_name', None)
        data.pop('hostname', None)

        return cls(**data)


class FolderPickerScreen(ModalScreen):
    """Folder picker screen for selecting workspace."""
    
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]
    
    def __init__(self, start_path: Optional[Path] = None):
        super().__init__()
        # Default to current working directory for convenience; fall back to home.
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
            # Wrap the tree to keep the dialog usable on small terminals.
            with ScrollableContainer(id="folder-tree-container"):
                yield DirectoryTree(str(self.start_path), id="folder-tree")
            with Horizontal(id="folder-picker-buttons"):
                yield Button("Select", variant="primary", id="select-button")
                yield Button("Cancel", variant="default", id="cancel-button")
    
    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Handle directory selection in the tree."""
        self.selected_path = Path(event.path)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Fallback: if a file is selected, treat its parent directory as the workspace."""
        self.selected_path = Path(event.path).parent
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-button":
            if self.selected_path:
                self.dismiss(self.selected_path)
        elif event.button.id == "cancel-button":
            self.dismiss(None)


class CreateInstanceScreen(ModalScreen):
    """Modal screen for creating new instances."""
    
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

            # Scrollable form so the dialog works on small terminals.
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

                yield Label("VNC Port:")
                yield Input(placeholder="5901", value="5901", id="vnc-port-input")

                # Get current user ID for PUID/PGID defaults
                try:
                    current_user = pwd.getpwuid(os.getuid())
                    default_puid = str(current_user.pw_uid)
                    default_pgid = str(current_user.pw_gid)
                except Exception:
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
        # Ensure the dialog is immediately usable with keyboard.
        self.query_one("#create-form", ScrollableContainer).focus()
        self.query_one("#name-input", Input).focus()

        # Apply initial sizing (otherwise the first paint can clip the bottom buttons).
        self._update_form_height()

    def on_resize(self, _: events.Resize) -> None:
        self._update_form_height()

    def _update_form_height(self) -> None:
        """Keep the scrollable form sized so the bottom button row remains visible."""
        try:
            form = self.query_one("#create-form", ScrollableContainer)
        except Exception:
            return

        # Leave space for: title + button row + borders/padding.
        available = max(5, self.app.size.height - 10)
        form.styles.height = available

    def action_focus_next(self) -> None:
        # Ensure Tab advances focus even if the Input widget swallows it.
        self.app.action_focus_next()

    def action_focus_previous(self) -> None:
        self.app.action_focus_previous()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "browse-button":
            self.app.push_screen(FolderPickerScreen(), self.handle_folder_selection)
        elif event.button.id == "create-button":
            self.create_instance()
        elif event.button.id == "cancel-button":
            self.app.pop_screen()
    
    def create_instance(self) -> None:
        """Create the instance with current form values."""
        name = self.query_one("#name-input", Input).value
        if not name:
            return
        
        if not self.workspace_folder:
            return  # Must have workspace folder
        
        cpu_select = self.query_one("#cpu-select", Select)
        memory_select = self.query_one("#memory-select", Select) 
        priority_select = self.query_one("#priority-select", Select)
        
        # Get values safely - Convert to string first, then to int
        try:
            cpu_value = str(cpu_select.value) if cpu_select.value else "2"
            cpu_cores = int(cpu_value)
        except (ValueError, TypeError, AttributeError):
            cpu_cores = 2
            
        try:
            memory_value = str(memory_select.value) if memory_select.value else "4096"
            memory_mb = int(memory_value)
        except (ValueError, TypeError, AttributeError):
            memory_mb = 4096
            
        try:
            priority_value = str(priority_select.value) if priority_select.value else "low"
            priority = priority_value
        except (ValueError, TypeError, AttributeError):
            priority = "low"
            
        ssh_port = int(self.query_one("#ssh-port-input", Input).value or "2222")
        vnc_port = int(self.query_one("#vnc-port-input", Input).value or "5901")
        puid = int(self.query_one("#puid-input", Input).value or "1000")
        pgid = int(self.query_one("#pgid-input", Input).value or "1000")
        
        instance = ToadboxInstance(
            name=name,
            workspace_folder=str(self.workspace_folder),
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            priority=priority,
            ssh_port=ssh_port,
            vnc_port=vnc_port,
            puid=puid,
            pgid=pgid
        )
        
        # Access the main app through the screen's app reference
        app_manager = self.app
        if hasattr(app_manager, 'create_instance'):
            app_manager.create_instance(instance)
        self.app.pop_screen()
    
    def handle_folder_selection(self, selected_path: Optional[Path]) -> None:
        """Handle folder selection result."""
        if selected_path:
            self.workspace_folder = selected_path
            # Update the label
            workspace_label = self.query_one("#workspace-label", Label)
            workspace_label.update(str(selected_path))
            # Update name input if it's empty
            name_input = self.query_one("#name-input", Input)
            if not name_input.value:
                name_input.value = selected_path.name


class StartupScreen(ModalScreen):
    """Startup screen showing running instances and options."""
    
    BINDINGS = [
        Binding("escape,q", "quit", "Quit"),
        Binding("c", "create_new", "Create New"),
        Binding("enter", "connect", "Connect"),
    ]
    
    def compose(self) -> ComposeResult:
        with Vertical(id="startup-container"):
            yield Static("🐸 Toadbox Manager", id="title")
            yield Static("Select an instance to connect to or create a new one:", id="subtitle")
            yield DataTable(id="running-instances-table")
            with Horizontal(id="button-container"):
                yield Button("Create New Instance", id="create-btn", variant="primary")
                yield Button("Refresh", id="refresh-btn")
                yield Button("Quit", id="quit-btn", variant="error")
    
    def on_mount(self) -> None:
        """Initialize the startup screen."""
        table = self.query_one("#running-instances-table", DataTable)
        table.add_columns("Name", "Status", "SSH Port", "VNC Port", "Action")
        self.refresh_instances()
    
    def refresh_instances(self) -> None:
        """Refresh the instances table."""
        table = self.query_one("#running-instances-table", DataTable)
        table.clear()
        
        running_instances = []
        
        # Try to get Docker client
        try:
            docker_client = docker.from_env()
            
            # Get all containers with toadbox in name
            containers = docker_client.containers.list(all=True, filters={"name": "toadbox"})
            
            for container in containers:
                container_name = container.name if container.name else "unknown"
                name = container_name.replace("toadbox_", "").replace("toadbox-", "")
                status = "Running" if container.status == "running" else "Stopped"
                
                # Get port mappings
                ports = container.ports or {}
                ssh_port_info = ports.get("22/tcp", [{}])
                vnc_port_info = ports.get("5901/tcp", [{}])
                
                ssh_port = ssh_port_info[0].get("HostPort", "N/A") if ssh_port_info else "N/A"
                vnc_port = vnc_port_info[0].get("HostPort", "N/A") if vnc_port_info else "N/A"
                action = "Connect" if container.status == "running" else "Start"
                
                # Only show running containers in the startup list.
                if container.status == "running":
                    table.add_row(name, status, ssh_port, vnc_port, action, key=name)
                    running_instances.append(name)
                    
        except Exception as e:
            table.add_row("Error", f"Failed to load: {e}", "-", "-", "-", key="error")
        
        # Update subtitle with running count
        subtitle = self.query_one("#subtitle", Static)
        if running_instances:
            subtitle.update(f"Found {len(running_instances)} running instance(s). Select to connect or create a new one:")
        else:
            subtitle.update("No running instances found. Create a new one to get started:")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "create-btn":
            self.action_create_new()
        elif event.button.id == "refresh-btn":
            self.refresh_instances()
        elif event.button.id == "quit-btn":
            self.action_quit()
    
    def action_create_new(self) -> None:
        """Create a new instance."""
        self.app.push_screen(FolderPickerScreen(), self.handle_folder_for_create)
    
    def handle_folder_for_create(self, selected_path: Optional[Path]) -> None:
        """Handle folder selection for creating new instance."""
        if selected_path:
            self.app.push_screen(CreateInstanceScreen(selected_path), self.handle_create_result)
        else:
            self.dismiss(None)
    
    def handle_create_result(self, result) -> None:
        """Handle create instance result."""
        if result:
            self.dismiss(("created", result))
        else:
            self.dismiss(None)
    
    def action_connect(self) -> None:
        """Connect to selected instance."""
        table = self.query_one("#running-instances-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is None:
            return
        try:
            row_key = table.get_row_key(cursor_row)
        except Exception:
            # Table is empty or cursor is invalid.
            return
        if row_key and row_key not in ["error", "nodocker"]:
            self.dismiss(("connect", row_key))
    
    def action_quit(self) -> None:
        """Quit the application."""
        self.dismiss(None)


class InstanceManagerApp(App):
    """Main application class."""
    
    BINDINGS = [
        Binding("c", "create_instance", "Create Instance"),
        Binding("s", "start_instance", "Start Instance"), 
        Binding("t", "stop_instance", "sTop Instance"),
        Binding("d", "delete_instance", "Delete Instance"),
        Binding("i", "connect_ssh", "SSH Connect"),
        Binding("v", "connect_vnc", "VNC Connect"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("h,?", "help", "Help"),
        Binding("ctrl+s", "screenshot", "Take Screenshot"),
    ]
    
    CSS = """
    DataTable {
        border: solid $primary;
        height: 1fr;
    }
    
    .status-running {
        color: green;
        text-style: bold;
    }
    
    .status-stopped {
        color: yellow;
    }
    
    .status-error {
        color: red;
        text-style: bold;
    }
    
    #main-container {
        height: 100%;
        layout: grid;
        grid-size: 1 1;
        grid-columns: 1fr;
        grid-rows: 1fr;
    }
    
    #instances-panel {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    
    #help-panel {
        display: none;
    }
    
    #help-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 0 0 1 0;
    }
    
    .help-section {
        margin: 1 0;
    }
    
    .help-key {
        color: $accent;
        text-style: bold;
    }
    
    .help-desc {
        color: $text;
    }
    
    #startup-container {
        width: 100%;
        height: 100%;
        background: $surface;
        border: none;
        padding: 1;
    }
    
    #title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    
    #subtitle {
        text-align: center;
        margin: 0 0 2 0;
        color: $text-muted;
    }
    
    #button-container {
        align: center middle;
        margin-top: 2;
    }
    
    #running-instances-table {
        margin: 1 0;
        height: 1fr;
    }
    
    #create-dialog, #folder-picker-dialog, #help-dialog {
        align: center middle;
        width: 100%;
        height: 100%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #create-dialog {
        padding: 1;
        layout: vertical;
    }

    #create-form {
        height: 1fr;
        margin: 1 0;
    }

    .button-row {
        dock: bottom;
        align: center middle;
        height: 3;
        margin-top: 0;
    }

    #workspace-row {
        width: 100%;
    }

    #name-browse-row {
        width: 100%;
        margin: 0 0 1 0;
        height: 3;
        align: left middle;
    }

    #name-input {
        width: 1fr;
        margin-right: 1;
        height: 3;
    }

    #browse-button {
        height: 3;
    }

    #workspace-label {
        width: 1fr;
        margin-right: 1;
    }

    .two-col {
        width: 100%;
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        grid-rows: auto;
        margin: 1 0;
    }

    .col {
        width: 100%;
    }

    .col:first-child {
        margin-right: 1;
    }

    Input, Select {
        width: 100%;
    }

    #folder-tree-container {
        height: 1fr;
        border: solid $primary;
        margin: 1 0;
    }
    
    #help-content {
        height: 1fr;
        margin: 1 0;
    }
    
    .dialog-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    
    
    """
    
    def __init__(self):
        super().__init__()
        self.config_file = Path.home() / ".toadbox-manager.json"
        self.instances: Dict[str, ToadboxInstance] = {}
        self.docker_client = None
        self.load_config()
        
        # Docker client preflight: on macOS/Linux this typically fails when the daemon isn't running
        # or when the Docker socket isn't accessible.
        self.console = Console()
        try:
            self.docker_client = docker.from_env()
            # Force a ping so we fail early with a clearer error.
            self.docker_client.ping()
        except DockerException as e:
            self.docker_client = None
            self.console.print("[red]Failed to connect to Docker.[/red]")
            self.console.print(f"[red]{e}[/red]")
            self.console.print(
                "[yellow]Make sure Docker Desktop (or dockerd) is running and your user can access the Docker socket.[/yellow]"
            )
    
    def generate_docker_compose(self, instance: ToadboxInstance) -> Dict[str, Any]:
        """Generate docker-compose configuration for an instance."""
        folder_path = Path(instance.workspace_folder)
        folder_name = folder_path.name
        service_name = instance.service_name
        
        compose_config = {
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
                        "DISPLAY=:1"
                    ],
                    "ports": [
                        f"{instance.ssh_port}:22",
                        f"{instance.vnc_port}:5901"
                    ],
                    "volumes": [
                        f"{instance.workspace_folder}:/workspace",
                        f"{service_name}_docker_data:/var/lib/docker",
                        f"{service_name}_home:/home/user"
                    ],
                    "networks": ["toadbox_network"],
                    "privileged": True,
                    "deploy": {
                        "resources": {
                            "limits": {
                                "cpus": f"{instance.cpu_cores}",
                                "memory": f"{instance.memory_mb}M"
                            }
                        }
                    }
                }
            },
            "volumes": {
                f"{service_name}_docker_data": {
                    "name": f"{service_name}_docker_data"
                },
                f"{service_name}_home": {
                    "name": f"{service_name}_home"
                }
            },
            "networks": {
                "toadbox_network": {
                    "driver": "bridge"
                }
            }
        }
        
        return compose_config
    
    def save_docker_compose(self, instance: ToadboxInstance) -> Path:
        """Save docker-compose file for an instance."""
        compose_config = self.generate_docker_compose(instance)
        
        # Create .toadbox directory in workspace
        toadbox_dir = Path(instance.workspace_folder) / ".toadbox"
        toadbox_dir.mkdir(exist_ok=True)
        
        compose_file = toadbox_dir / "docker-compose.yml"
        with open(compose_file, 'w', encoding='utf-8') as f:
            yaml.dump(compose_config, f, default_flow_style=False)
        
        instance.compose_file = str(compose_file)
        return compose_file
    
    def run_docker_compose(self, instance: ToadboxInstance, action: str = "up") -> tuple[bool, str]:
        """Run docker-compose command for an instance.

        Returns (ok, message) where message contains stderr/stdout for diagnostics.
        """
        if not instance.compose_file:
            self.save_docker_compose(instance)
        
        if not instance.compose_file:
            return False, "Missing compose file"
        compose_dir = Path(instance.compose_file).parent
        
        # Set environment variables for docker-compose
        env = os.environ.copy()
        env.update({
            "COMPOSE_PROJECT_NAME": instance.service_name,
            "WORKSPACE_PATH": instance.workspace_folder,
            "SSH_PORT": str(instance.ssh_port),
            "VNC_PORT": str(instance.vnc_port),
            "PUID": str(instance.puid),
            "PGID": str(instance.pgid),
            "CPU_LIMITS": str(instance.cpu_cores),
            "MEMORY_LIMITS": f"{instance.memory_mb}M"
        })

        # Prefer modern Docker Compose plugin (`docker compose`) but fall back to legacy `docker-compose`.
        # Some environments have a `docker` binary without the compose plugin; detect that explicitly.
        compose_file = str(Path(instance.compose_file))
        docker_bin = shutil.which("docker")
        docker_compose_bin = shutil.which("docker-compose")

        use_docker_compose_plugin = False
        if docker_bin:
            try:
                probe = subprocess.run(
                    [docker_bin, "compose", "version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                use_docker_compose_plugin = probe.returncode == 0
            except OSError:
                use_docker_compose_plugin = False
            except subprocess.TimeoutExpired:
                use_docker_compose_plugin = False

        if use_docker_compose_plugin:
            cmd: list[str] = [docker_bin, "compose", "-f", compose_file, "-p", instance.service_name, action]  # type: ignore[list-item]
        elif docker_compose_bin:
            cmd = [docker_compose_bin, "-f", compose_file, "-p", instance.service_name, action]
        else:
            return False, "Neither 'docker compose' nor 'docker-compose' is available"
        
        if action == "up":
            cmd.extend(["-d"])  # detached mode
        
        try:
            result = subprocess.run(
                cmd,
                cwd=compose_dir,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )
            output = (result.stderr or "").strip() or (result.stdout or "").strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "compose timed out"
        except OSError as e:
            return False, f"Failed to run compose: {e}"
    
    def get_compose_status(self, instance: ToadboxInstance) -> InstanceStatus:
        """Get status of docker-compose service."""
        if not instance.compose_file:
            return InstanceStatus.STOPPED
        
        compose_dir = Path(instance.compose_file).parent
        
        # Set environment variables for docker-compose
        env = os.environ.copy()
        env.update({
            "COMPOSE_PROJECT_NAME": instance.service_name,
            "WORKSPACE_PATH": instance.workspace_folder,
            "SSH_PORT": str(instance.ssh_port),
            "VNC_PORT": str(instance.vnc_port),
            "PUID": str(instance.puid),
            "PGID": str(instance.pgid),
            "CPU_LIMITS": str(instance.cpu_cores),
            "MEMORY_LIMITS": f"{instance.memory_mb}M"
        })
        
        try:
            compose_file = str(Path(instance.compose_file))
            docker_bin = shutil.which("docker")
            docker_compose_bin = shutil.which("docker-compose")

            use_docker_compose_plugin = False
            if docker_bin:
                probe = subprocess.run(
                    [docker_bin, "compose", "version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                use_docker_compose_plugin = probe.returncode == 0

            if use_docker_compose_plugin:
                ps_cmd = [docker_bin, "compose", "-f", compose_file, "-p", instance.service_name, "ps", "--services", "--filter", "status=running"]  # type: ignore[list-item]
            elif docker_compose_bin:
                ps_cmd = [docker_compose_bin, "-f", compose_file, "-p", instance.service_name, "ps", "--services", "--filter", "status=running"]
            else:
                return InstanceStatus.ERROR
            result = subprocess.run(
                ps_cmd,
                cwd=compose_dir,
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                check=False,
            )
            
            if result.returncode == 0 and instance.service_name in result.stdout:
                return InstanceStatus.RUNNING
            else:
                return InstanceStatus.STOPPED
                
        except Exception:
            return InstanceStatus.ERROR
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="instances-panel"):
                yield Label("🐸 Toadbox Instances", classes="panel-title")
                yield DataTable(id="instances-table")
                yield Static(id="status-bar")
            with Vertical(id="help-panel"):
                yield Label("Help", id="help-title")
                yield Static("[help-section][help-key]c[/help-key] - Create new instance\n[help-desc]Browse and select a workspace folder[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]s[/help-key] - Start selected instance\n[help-desc]Launch the Docker container[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]t[/help-key] - sTop selected instance\n[help-desc]Stop the running container[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]d[/help-key] - Delete selected instance\n[help-desc]Remove container and volumes[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]i[/help-key] - SSH connect\n[help-desc]Connect via SSH to selected instance[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]v[/help-key] - VNC connect\n[help-desc]Connect via VNC to selected instance[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]r[/help-key] - Refresh list\n[help-desc]Update instance statuses[/help-desc][/help-section]", classes="help-text")
                yield Static("[help-section][help-key]q[/help-key] - Quit\n[help-desc]Exit the manager[/help-desc][/help-section]", classes="help-text")
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the application."""
        table = self.query_one("#instances-table", DataTable)
        
        # Add columns
        table.add_columns("Name", "Status", "CPU", "Memory", "SSH", "VNC", "Priority")
        
        # Show startup screen
        if self.docker_client:
            self.push_screen(StartupScreen(), self.handle_startup_result)
        else:
            # No Docker connection, just load saved instances
            self.refresh_table()
    
    def handle_startup_result(self, result) -> None:
        """Handle startup screen result."""
        if not result:
            # User cancelled, just show empty table
            self.refresh_table()
            return
        
        action, data = result
        if action == "created":
            self.refresh_table()
        elif action == "connect":
            self.quick_connect(data)
        else:
            self.refresh_table()
    
    def get_running_containers(self) -> List[str]:
        """Get list of running toadbox containers."""
        if not self.docker_client:
            return []
        
        try:
            containers = self.docker_client.containers.list(filters={"name": "toadbox"})
            names = []
            for c in containers:
                if c.name:
                    name = c.name.replace("toadbox_", "").replace("toadbox-", "")
                    if c.status == "running":
                        names.append(name)
            return names
        except Exception:
            return []
    
    def quick_connect(self, instance_name: str) -> None:
        """Quick connect to a running instance."""
        if not self.docker_client:
            self.show_error("Docker client not available")
            return
        
        try:
            containers = self.docker_client.containers.list(filters={"name": f"toadbox_{instance_name}"})
            if containers:
                container = containers[0]
                # Get port mappings
                ports = container.ports or {}
                ssh_port_info = ports.get("22/tcp", [{}])
                vnc_port_info = ports.get("5901/tcp", [{}])
                
                ssh_port = ssh_port_info[0].get("HostPort", "2222") if ssh_port_info else "2222"
                vnc_port = vnc_port_info[0].get("HostPort", "5901") if vnc_port_info else "5901"
                
                # Create temporary instance object for connection
                temp_instance = ToadboxInstance(
                    name=instance_name,
                    workspace_folder="",  # Not needed for connection
                    ssh_port=int(ssh_port) if ssh_port.isdigit() else 2222,
                    vnc_port=int(vnc_port) if vnc_port.isdigit() else 5901,
                    status=InstanceStatus.RUNNING
                )
                self.connect_ssh(temp_instance)
                self.exit()
        except Exception as e:
            self.show_error(f"Failed to connect to {instance_name}: {e}")
        
        # Load instances table if staying in app
        table = self.query_one("#instances-table", DataTable)
        if not hasattr(table, 'columns'):
            table.add_columns("Name", "Status", "CPU", "Memory", "SSH", "VNC", "Priority")
        self.refresh_table()
        table.focus()
    
    def load_config(self) -> None:
        """Load instances configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    instances_data = data.get('instances', {})
                    self.instances = {
                        name: ToadboxInstance.from_dict(inst_data)
                        for name, inst_data in instances_data.items()
                    }
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def save_config(self) -> None:
        """Save instances configuration to file."""
        try:
            data = {
                'instances': {
                    name: instance.to_dict()
                    for name, instance in self.instances.items()
                }
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.show_error(f"Failed to save config: {e}")
    
    def refresh_table(self) -> None:
        """Refresh the instances table."""
        table = self.query_one("#instances-table", DataTable)
        table.clear()
        
        for instance in self.instances.values():
            status_style = f"status-{instance.status.value}"
            table.add_row(
                instance.name,
                f"[{status_style}]{instance.status.value}[/{status_style}]",
                str(instance.cpu_cores),
                f"{instance.memory_mb}MB",
                str(instance.ssh_port),
                str(instance.vnc_port),
                instance.priority,
                key=instance.name
            )
        
        # Update status bar
        status_bar = self.query_one("#status-bar", Static)
        running = sum(1 for i in self.instances.values() if i.status == InstanceStatus.RUNNING)
        status_bar.update(f"Instances: {len(self.instances)} | Running: {running}")
    
    def get_selected_instance(self) -> Optional[ToadboxInstance]:
        """Get the currently selected instance."""
        table = self.query_one("#instances-table", DataTable)
        if table.cursor_row is None:
            return None
        
        # Get the key for the current row
        try:
            row_data = table.get_row_at(table.cursor_row)
            if row_data and len(row_data) > 0:
                instance_name = str(row_data[0])  # First column is the name
                return self.instances.get(instance_name)
        except Exception:
            pass
        return None
    
    def action_create_instance(self) -> None:
        """Show create instance dialog."""
        self.push_screen(FolderPickerScreen(), self.handle_folder_create)
    
    def handle_folder_create(self, selected_path: Optional[Path]) -> None:
        """Handle folder selection for create."""
        if selected_path:
            self.push_screen(CreateInstanceScreen(selected_path))
    
    def create_instance(self, instance: ToadboxInstance) -> None:
        """Create a new instance."""
        if instance.name in self.instances:
            self.show_error(f"Instance '{instance.name}' already exists")
            return
        
        self.instances[instance.name] = instance
        self.save_config()
        self.refresh_table()
    
    def action_start_instance(self) -> None:
        """Start the selected instance."""
        instance = self.get_selected_instance()
        if not instance:
            self.show_error("No instance selected")
            return
        asyncio.create_task(self.start_instance_async(instance))
    
    async def start_instance_async(self, instance: ToadboxInstance) -> None:
        """Start an instance asynchronously using docker-compose."""
        try:
            instance.status = InstanceStatus.STARTING
            self.refresh_table()
            
            # Start using docker-compose
            ok, msg = self.run_docker_compose(instance, "up")
            if ok:
                # Update status
                instance.status = self.get_compose_status(instance)
                self.save_config()
                self.refresh_table()
            else:
                instance.status = InstanceStatus.ERROR
                self.refresh_table()
                detail = f": {msg}" if msg else ""
                self.show_error(f"Failed to start instance '{instance.name}'{detail}")
                
        except Exception as e:
            instance.status = InstanceStatus.ERROR
            self.refresh_table()
            self.show_error(f"Failed to start instance: {e}")
    
    def action_stop_instance(self) -> None:
        """Stop the selected instance."""
        instance = self.get_selected_instance()
        if instance:
            asyncio.create_task(self.stop_instance_async(instance))
    
    async def stop_instance_async(self, instance: ToadboxInstance) -> None:
        """Stop an instance asynchronously using docker-compose."""
        try:
            instance.status = InstanceStatus.STOPPING
            self.refresh_table()
            
            # Stop using docker-compose
            ok, msg = self.run_docker_compose(instance, "stop")
            if ok:
                instance.status = InstanceStatus.STOPPED
                self.save_config()
                self.refresh_table()
            else:
                instance.status = InstanceStatus.ERROR
                self.refresh_table()
                detail = f": {msg}" if msg else ""
                self.show_error(f"Failed to stop instance '{instance.name}'{detail}")
                
        except Exception as e:
            instance.status = InstanceStatus.ERROR
            self.refresh_table()
            self.show_error(f"Failed to stop instance: {e}")
    
    def action_delete_instance(self) -> None:
        """Delete the selected instance."""
        instance = self.get_selected_instance()
        if instance:
            asyncio.create_task(self.delete_instance_async(instance))
    
    async def delete_instance_async(self, instance: ToadboxInstance) -> None:
        """Delete an instance asynchronously."""
        if instance.status == InstanceStatus.RUNNING:
            await self.stop_instance_async(instance)
        
        try:
            # Remove using docker-compose
            ok, msg = self.run_docker_compose(instance, "down")
            if ok:
                # Remove volumes
                if instance.compose_file:
                    compose_dir = Path(instance.compose_file).parent
                    
                    # Set environment variables for docker-compose
                    env = os.environ.copy()
                    env.update({
                        "COMPOSE_PROJECT_NAME": instance.service_name,
                        "WORKSPACE_PATH": instance.workspace_folder,
                        "SSH_PORT": str(instance.ssh_port),
                        "VNC_PORT": str(instance.vnc_port),
                        "PUID": str(instance.puid),
                        "PGID": str(instance.pgid),
                        "CPU_LIMITS": str(instance.cpu_cores),
                        "MEMORY_LIMITS": f"{instance.memory_mb}M"
                    })
                    
                    down_cmd = (
                        ["docker", "compose", "-f", str(Path(instance.compose_file)), "-p", instance.service_name, "down", "-v"]
                        if shutil.which("docker")
                        else ["docker-compose", "-f", str(Path(instance.compose_file)), "-p", instance.service_name, "down", "-v"]
                    )
                    subprocess.run(
                        down_cmd,
                        cwd=compose_dir,
                        capture_output=True,
                        timeout=30,
                        env=env,
                        check=False,
                        text=True,
                    )
            else:
                detail = f": {msg}" if msg else ""
                self.show_error(f"Failed to remove instance '{instance.name}'{detail}")
            
            # Remove instance from config
            del self.instances[instance.name]
            self.save_config()
            self.refresh_table()
            
        except Exception as e:
            self.show_error(f"Failed to delete instance: {e}")
    
    def action_connect_ssh(self) -> None:
        """Connect to selected instance via SSH."""
        instance = self.get_selected_instance()
        if instance and instance.status == InstanceStatus.RUNNING:
            self.connect_ssh(instance)
        else:
            self.show_error("Select a running instance to connect via SSH")
    
    def connect_ssh(self, instance: ToadboxInstance) -> None:
        """Connect to instance via SSH."""
        try:
            cmd = [
                'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                '-p', str(instance.ssh_port), 'user@localhost'
            ]
            
            # Suspend the TUI and run SSH
            self.exit()
            subprocess.run(cmd, check=True)
            
        except subprocess.CalledProcessError as e:
            print(f"SSH connection failed: {e}")
        except FileNotFoundError:
            print("SSH client not found. Please install OpenSSH client.")
        except Exception as e:
            print(f"Failed to connect via SSH: {e}")
    
    def action_connect_vnc(self) -> None:
        """Connect to selected instance via VNC."""
        instance = self.get_selected_instance()
        if instance and instance.status == InstanceStatus.RUNNING:
            self.connect_vnc(instance)
        else:
            self.show_error("Select a running instance to connect via VNC")
    
    def connect_vnc(self, instance: ToadboxInstance) -> None:
        """Connect to instance via VNC."""
        try:
            # Try common VNC viewers
            vnc_viewers = [
                ['vncviewer', f'localhost:{instance.vnc_port}'],
                ['remmina', '-c', f'vnc://localhost:{instance.vnc_port}'],
                ['tightvncviewer', f'localhost:{instance.vnc_port}']
            ]
            
            for cmd in vnc_viewers:
                try:
                    self.exit()
                    subprocess.run(cmd, check=True)
                    return
                except FileNotFoundError:
                    continue
                except subprocess.CalledProcessError:
                    continue
            
            print("No VNC viewer found. Please install vncviewer or remmina.")
                
        except Exception as e:
            print(f"Failed to connect via VNC: {e}")
    
    def action_refresh(self) -> None:
        """Refresh instance statuses."""
        asyncio.create_task(self.refresh_statuses_async())

    async def refresh_statuses_async(self) -> None:
        """Refresh all instance statuses from docker-compose."""
        for instance in self.instances.values():
            instance.status = self.get_compose_status(instance)

        self.save_config()
        self.refresh_table()
    
    def action_help(self) -> None:
        """Show help dialog."""
        help_text = """
🐸 Toadbox Manager Help

KEYBOARD SHORTCUTS:
[c] Create New Instance    - Browse and select a workspace folder
[s] Start Instance         - Launches selected toadbox container
[t] sTop Instance          - Stop running container
[d] Delete Instance        - Remove container and all data volumes
[i] SSH Connect           - Connect to selected instance via SSH
[v] VNC Connect           - Connect to selected instance via VNC
[r] Refresh               - Update all instance statuses
[Ctrl+S] Screenshot         - Take a screenshot of the TUI
[q] Quit                  - Exit the manager

NAVIGATION:
↑/↓ - Move cursor up/down
Enter - Connect to selected instance
Tab  - Switch between panels

TIPS:
• Use the folder picker to easily select workspaces
• Container names are automatically based on folder names
• PUID/PGID ensure proper file permissions
• Docker-compose handles cleanup and dependencies
• Press Ctrl+S to capture screenshots for documentation
        """
        
        self.app.push_screen(HelpScreen(help_text))
    
    def action_screenshot(self) -> None:
        """Take a screenshot of the TUI."""
        try:
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"toadbox_manager_screenshot_{timestamp}.svg"
            path = Path.cwd() / filename
            
            # Show notification in status bar
            status_bar = self.query_one("#status-bar", Static)
            status_bar.update(f"[green]📸 Taking screenshot...[/green]")
            
            # Use basic screenshot capture
            try:
                # Try newer Textual screenshot API
                self.app.save_screenshot(str(path))
                status_bar.update(f"[green]📸 Screenshot saved to: {path}[/green]")
            except AttributeError:
                # Fallback for older Textual versions
                status_bar.update("[yellow]📸 Screenshot not available in this Textual version[/yellow]")
        except Exception as e:
            status_bar = self.query_one("#status-bar", Static)
            status_bar.update(f"[red]Failed to take screenshot: {e}[/red]")

    def show_error(self, message: str) -> None:
        """Show an error message."""
        self.bell()
        status_bar = self.query_one("#status-bar", Static)
        status_bar.update(f"[red]Error: {message}[/red]")


class HelpScreen(ModalScreen):
    """Help screen showing keyboard shortcuts and tips."""
    
    BINDINGS = [("escape,q", "dismiss", "Close")]
    
    def __init__(self, help_text: str):
        super().__init__()
        self.help_text = help_text
    
    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Label("🐸 Help", classes="dialog-title")
            yield Static(self.help_text, id="help-content")
            yield Button("Close", variant="primary", id="close-button")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-button":
            self.dismiss()


def main():
    """Main entry point."""
    app = InstanceManagerApp()
    app.run()


if __name__ == "__main__":
    main()