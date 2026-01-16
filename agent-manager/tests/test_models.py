import json
import pytest
from toadbox_manager.models import ToadboxInstance, InstanceStatus


def test_toadbox_instance_serialization_roundtrip():
    inst = ToadboxInstance(
        name="test",
        workspace_folder="/tmp/workspace",
        cpu_cores=4,
        memory_mb=8192,
        priority="high",
        ssh_port=2223,
        rdp_port=3391,
        puid=1001,
        pgid=1001,
        status=InstanceStatus.RUNNING,
    )

    js = inst.to_json()
    data = json.loads(js)
    assert data["name"] == "test"
    assert data["status"] == "running"

    inst2 = ToadboxInstance.from_dict(data)
    assert inst2.name == inst.name
    assert inst2.status == inst.status


def test_service_name_and_hostname():
    inst = ToadboxInstance(name="my-box", workspace_folder="/home/user/my-box")
    assert inst.service_name == "my_box"
    assert inst.hostname.startswith("toadbox-my-box")


def test_from_dict_legacy_vnc_field():
    payload = {
        "name": "legacy",
        "workspace_folder": "/tmp/legacy",
        "vnc_port": 5901,
    }
    inst = ToadboxInstance.from_dict(payload)
    assert inst.rdp_port == 5901
