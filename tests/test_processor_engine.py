import os
from pathlib import Path

from requesttool import processor_engine


def test_find_node_binary_prefers_configured_binary_path(monkeypatch, tmp_path: Path):
    node_binary = tmp_path / "node.exe"
    node_binary.write_text("", encoding="utf-8")
    monkeypatch.setenv("REQUESTTOOL_NODE_BIN", str(node_binary))
    monkeypatch.delenv("NODE_BINARY", raising=False)
    monkeypatch.setattr("requesttool.processor_engine.shutil.which", lambda _name: None)

    assert processor_engine._find_node_binary() == str(node_binary)


def test_find_node_binary_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.delenv("REQUESTTOOL_NODE_BIN", raising=False)
    monkeypatch.delenv("NODE_BINARY", raising=False)
    monkeypatch.setattr("requesttool.processor_engine.shutil.which", lambda name: f"/usr/bin/{name}")

    expected_binary = "node.exe" if os.name == "nt" else "node"
    assert processor_engine._find_node_binary() == f"/usr/bin/{expected_binary}"
