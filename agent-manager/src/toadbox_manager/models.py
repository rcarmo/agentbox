from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Optional
import re


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
    rdp_port: int = 3390
    puid: int = 1000
    pgid: int = 1000
    status: InstanceStatus = InstanceStatus.STOPPED
    compose_file: Optional[str] = None
    container_id: Optional[str] = None

    @property
    def service_name(self) -> str:
        """Generate docker-compose service name based on folder."""
        # Prefer a sanitized instance `name` if provided, otherwise fall back to workspace folder name
        base = self.name or Path(self.workspace_folder).name
        # sanitize: allow letters/numbers/underscore, convert other chars to underscore
        sanitized = re.sub(r"[^0-9a-zA-Z]+", "_", base).strip("_").lower()
        return sanitized or Path(self.workspace_folder).name.replace("-", "_").lower()

    @property
    def hostname(self) -> str:
        """Generate hostname based on folder."""
        # Use the instance name for hostname if available, otherwise workspace folder
        base = self.name or Path(self.workspace_folder).name
        sanitized = re.sub(r"[^0-9a-zA-Z]+", "-", base).strip("-").lower()
        return f"toadbox-{sanitized}"

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "ToadboxInstance":
        # Copy to avoid mutating caller data
        payload = dict(data)

        # Handle legacy field names (vnc_port) and status serialization
        if "status" in payload:
            payload["status"] = InstanceStatus(payload["status"])
        else:
            payload["status"] = InstanceStatus.STOPPED

        if "vnc_port" in payload and "rdp_port" not in payload:
            payload["rdp_port"] = payload.pop("vnc_port")

        payload.pop("service_name", None)
        payload.pop("hostname", None)
        return cls(**payload)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
