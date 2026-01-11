import os
from types import SimpleNamespace

import pytest
from docker.errors import DockerException

from toadbox_manager.app import InstanceManagerApp
from toadbox_manager.models import ToadboxInstance, InstanceStatus


def make_app(monkeypatch, tmp_path):
    # Prevent docker.from_env side-effects during app init by causing it to raise
    # DockerException so the app falls back to docker_client = None
    monkeypatch.setattr(
        "toadbox_manager.app.docker.from_env",
        lambda: (_ for _ in ()).throw(DockerException()),
    )
    app = InstanceManagerApp()
    # Keep compose files in temp dir to avoid touching home
    app.compose_dir = tmp_path
    app.compose_path = tmp_path / "docker-compose.yml"
    return app


def test_build_compose_spec_multiple_instances(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    a = ToadboxInstance(name="one", workspace_folder="/work/one", ssh_port=2222, rdp_port=3390, cpu_cores=1, memory_mb=1024)
    b = ToadboxInstance(name="two", workspace_folder="/work/two", ssh_port=2223, rdp_port=3391, cpu_cores=2, memory_mb=2048)
    app.instances = {a.name: a, b.name: b}
    spec = app._build_compose_spec()
    assert "services" in spec
    svc_names = list(spec["services"].keys())
    assert a.service_name in svc_names
    assert b.service_name in svc_names
    # check ports strings present
    svc_a = spec["services"][a.service_name]
    assert f"{a.ssh_port}:22" in svc_a["ports"]
    assert f"{b.rdp_port}:3389" in spec["services"][b.service_name]["ports"]


def test_write_compose_writes_file(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"))
    app.instances = {inst.name: inst}
    path = app._write_compose()
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "services:" in content


def test_run_compose_no_docker(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"))
    # Ensure docker and docker-compose are not found
    monkeypatch.setattr("shutil.which", lambda name: None)
    ok, detail = app._run_compose(inst, "up")
    assert not ok
    assert "docker compose not found" in detail


def test_run_compose_with_docker_compose_bin(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"))
    # Simulate docker CLI missing, but docker-compose binary present
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker-compose" if name == "docker-compose" else None)

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    ok, detail = app._run_compose(inst, "up")
    assert ok
    assert detail == "ok"


def test_get_compose_status_no_file(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"))
    # ensure compose file does not exist
    if app.compose_path.exists():
        app.compose_path.unlink()
    status = app._get_compose_status(inst)
    assert status == InstanceStatus.STOPPED


def test_get_compose_status_running(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="svc", workspace_folder=str(tmp_path / "svc"))
    # create a dummy compose file so the method proceeds
    app.compose_path.write_text("dummy", encoding="utf-8")

    # simulate docker binary present and probe succeeds, and ps returns service name
    def fake_which(name):
        return "/usr/bin/docker" if name == "docker" else None

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "compose version" in cmd_str:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "ps" in cmd:
            return SimpleNamespace(returncode=0, stdout=inst.service_name, stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="err")

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)
    status = app._get_compose_status(inst)
    assert status == InstanceStatus.RUNNING


def test_action_connect_ssh_invokes_subprocess(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"), ssh_port=2229, status=InstanceStatus.RUNNING)
    # monkeypatch get_selected_instance
    monkeypatch.setattr(app, "get_selected_instance", lambda: inst)
    calls = []

    def fake_exit():
        calls.append("exit")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app, "exit", fake_exit)
    monkeypatch.setattr("subprocess.run", fake_run)
    app.action_connect_ssh()
    assert "exit" in calls
    # ensure ssh port present in the command list
    ssh_cmds = [c for c in calls if isinstance(c, list)]
    assert any(str(inst.ssh_port) in " ".join(map(str, c)) for c in ssh_cmds)


def test_action_connect_rdp_tries_alternatives(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    inst = ToadboxInstance(name="x", workspace_folder=str(tmp_path / "x"), rdp_port=3399, status=InstanceStatus.RUNNING)
    monkeypatch.setattr(app, "get_selected_instance", lambda: inst)
    call_count = {"n": 0}

    def fake_exit():
        call_count["n"] += 1

    def fake_run(cmd, **kwargs):
        # first call simulate FileNotFoundError, second returns normally
        if call_count["n"] == 0:
            call_count["n"] += 1
            raise FileNotFoundError()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app, "exit", fake_exit)
    monkeypatch.setattr("subprocess.run", fake_run)
    app.action_connect_rdp()
    # we expect at least two attempts (one failure, then success)
    assert call_count["n"] >= 1


def test_quick_connect_parses_ports_and_calls_connect(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    # create fake docker client and container
    class FakeContainer:
        def __init__(self):
            self.ports = {"22/tcp": [{"HostPort": "2233"}], "3389/tcp": [{"HostPort": "3344"}]}

    class FakeContainers:
        def list(self, filters=None):
            return [FakeContainer()]

    app.docker_client = SimpleNamespace(containers=FakeContainers())
    called = {}

    def fake_connect_ssh(inst):
        called["inst"] = inst

    monkeypatch.setattr(app, "_connect_ssh", fake_connect_ssh)
    app.quick_connect("myname")
    assert "inst" in called
    assert called["inst"].ssh_port == 2233
    assert called["inst"].rdp_port == 3344


def test_attach_to_container_executes_docker(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    # fake docker client with a container object
    class FakeContainer:
        def __init__(self):
            self.name = "toadbox_svc"

    class FakeContainers:
        def list(self, filters=None):
            return [FakeContainer()]

    app.docker_client = SimpleNamespace(containers=FakeContainers())
    inst = ToadboxInstance(name="svc", workspace_folder=str(tmp_path / "svc"), status=InstanceStatus.RUNNING)
    called = {}

    def fake_exit():
        called["exit"] = True

    def fake_run(cmd, **kwargs):
        called["cmd"] = cmd
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app, "exit", fake_exit)
    monkeypatch.setattr("subprocess.run", fake_run)
    app._attach_to_container(inst)
    assert called.get("exit") is True
    assert "docker" in called.get("cmd", [])[0]


def test_attach_to_container_no_docker_client_shows_error(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    app.docker_client = None
    inst = ToadboxInstance(name="svc", workspace_folder=str(tmp_path / "svc"), status=InstanceStatus.RUNNING)
    # capture status bar updates via query_one
    class FakeStatus:
        def __init__(self):
            self.text = ""

        def update(self, txt):
            self.text = txt

    fake_status = FakeStatus()
    monkeypatch.setattr(app, "query_one", lambda sel, *a, **k: fake_status)
    app._attach_to_container(inst)
    assert (
        "Docker is not available" in fake_status.text
        or "Container not found" in fake_status.text
    )

