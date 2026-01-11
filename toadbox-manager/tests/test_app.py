from toadbox_manager.app import InstanceManagerApp
from toadbox_manager.models import ToadboxInstance, InstanceStatus


class DummyTable:
    def __init__(self, rows=None, cursor_row=None):
        self._rows = rows or []
        self.cursor_row = cursor_row

    @property
    def row_count(self):
        return len(self._rows)

    def get_row_at(self, idx):
        return self._rows[idx]


class DummyQuery:
    def __init__(self, table):
        self._table = table

    def query_one(self, selector, widget_type=None):
        return self._table


def test_suggest_ports_empty(monkeypatch, tmp_path):
    # isolate from real HOME/config
    monkeypatch.setattr("toadbox_manager.app.Path.home", lambda: tmp_path)
    app = InstanceManagerApp()
    # no instances
    ssh, rdp = app.suggest_ports()
    assert ssh == 2222
    assert rdp == 3390


def test_get_selected_instance_none_on_empty_table(monkeypatch, tmp_path):
    # isolate from real HOME/config
    monkeypatch.setattr("toadbox_manager.app.Path.home", lambda: tmp_path)
    app = InstanceManagerApp()
    dummy_table = DummyTable(rows=[], cursor_row=None)
    # monkeypatch query_one
    monkeypatch.setattr(app, "query_one", lambda s, *a, **k: dummy_table)
    assert app.get_selected_instance() is None


def test_get_selected_instance_returns_instance(monkeypatch, tmp_path):
    # isolate from real HOME/config
    monkeypatch.setattr("toadbox_manager.app.Path.home", lambda: tmp_path)
    app = InstanceManagerApp()
    inst = ToadboxInstance(name="foo", workspace_folder="/tmp/foo")
    app.instances["foo"] = inst
    dummy_table = DummyTable(rows=[("foo",)], cursor_row=0)
    monkeypatch.setattr(app, "query_one", lambda s, *a, **k: dummy_table)
    result = app.get_selected_instance()
    assert result is inst
