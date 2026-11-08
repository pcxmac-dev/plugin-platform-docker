"""Nothing in these tests runs docker or wsl, starts a process or reaches the network: every command is a stand-in's
(each test hands the plugin its runners, which answer with what docker gave: tests/data), a process started or a
connection made is refused, and no program is found on PATH (the library's docker.instances looks for docker there)."""
from __future__ import annotations

import shutil
import socket
import subprocess

import pytest


@pytest.fixture(autouse=True)
def nothing_runs(monkeypatch):
    def refused(*a, **k):
        raise AssertionError("a test started a process or reached for the network")
    monkeypatch.setattr(subprocess, "run", refused)
    monkeypatch.setattr(subprocess, "Popen", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    for name in ("LIMINAL_DOCKER_COMMAND", "LIMINAL_DOCKER_HOST", "LIMINAL_DOCKER_CONTEXT"):
        monkeypatch.delenv(name, raising=False)
