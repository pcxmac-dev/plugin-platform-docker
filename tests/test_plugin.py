"""Docker: the engines found (Docker inside Liminal-Ubuntu as the WSL plugin offers it, this machine's, a context's, a
host's), each one's version and state, the shown engine's containers, images, volumes and networks as the page draws
them, the engine chosen, the changes once confirmed and the refusals before them, the command line. Every command is a
stand-in's, answering with what docker gives (tests/data): nothing runs here, and a stopped distribution is never
asked (no `wsl -d` at all)."""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

import plugin_platform_docker as dk
import plugin_platform_docker.__main__ as cli
from liminal_libs.docker import DockerError, Instance
from liminal_libs.machines.wsl import Wsl, WslDistribution
from plugin_platform_docker import DockerPlugin, Refusal
from plugin_platform_docker import engines as eng

DATA = Path(__file__).parent / "data"
NO_DAEMON = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
UTC = timezone.utc


def recorded(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def rows(name: str) -> list[dict]:
    return [json.loads(line) for line in recorded(name).splitlines() if line.strip()]


class FakeEngine:
    """One Docker engine as a stand-in: its containers, images, volumes and networks as docker lists them (tests/data),
    changed by the commands it is given; each command's docker arguments kept."""

    def __init__(self, daemon=True, containers=None, images=None):
        self.daemon = daemon
        self.containers = rows("ps.jsonl") if containers is None else containers
        self.images = rows("images.jsonl") if images is None else images
        self.volumes, self.networks = rows("volumes.jsonl"), rows("networks.jsonl")
        self.asked: list[list[str]] = []

    def answer(self, args):
        self.asked.append(args)
        if args[:1] == ["version"]:
            return (0, recorded("version.json"), "") if self.daemon else (1, recorded("version-no-daemon.json"), NO_DAEMON)
        if not self.daemon:
            return 1, "", NO_DAEMON
        listing = {"ps": self.containers, "images": self.images, "volume": self.volumes, "network": self.networks}
        if args[0] in listing:
            return 0, "".join(json.dumps(r) + "\n" for r in listing[args[0]]), ""
        if args[0] == "logs":
            return 0, recorded("logs-out.txt"), recorded("logs-err.txt")
        if args[0] == "pull":
            repo, _, tag = args[1].partition(":")
            self.images.append({**self.images[0], "Repository": repo, "Tag": tag or "latest", "ID": "sha256:" + "5" * 64})
            return 0, recorded("pull.txt"), ""
        if args[0] == "rmi":
            gone = [i for i in self.images if f"{i['Repository']}:{i['Tag']}" == args[-1]]
            for i in gone:
                self.images.remove(i)
            return 0, f"Untagged: {args[-1]}\nDeleted: {gone[0]['ID'] if gone else ''}\n", ""
        name = args[-1]
        c = next((c for c in self.containers if c["Names"] == name), None)
        if c is None:
            return 1, "", f"Error response from daemon: No such container: {name}"
        if args[0] in ("start", "restart"):
            c.update(State="running", Status="Up Less than a second")
        elif args[0] == "stop":
            c.update(State="exited", Status="Exited (0) Less than a second ago")
        elif args[0] == "rm":
            if c["State"] == "running" and "-f" not in args:
                return 1, "", f'Error response from daemon: cannot remove container "/{name}": container is running'
            self.containers.remove(c)
        else:
            return 1, "", f"unknown command: docker {' '.join(args)}"
        return 0, name + "\n", ""


class Docker:
    """The runner the plugin is given: each command to the engine its argv names (WSL's distribution, a context, the
    host, else this machine's), the argv kept whole."""

    def __init__(self, **engines):
        self.engines = engines
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        at = next(i for i, a in enumerate(argv) if os.path.basename(a) in ("docker", "docker.exe"))
        args, key = list(argv[at + 1:]), "wsl" if argv[0] == "wsl" else "local"
        while args[:1] in (["--context"], ["-H"]):
            key, args = (args[1] if args[0] == "--context" else "host"), args[2:]
        return self.engines[key].answer(args)


def u16(text: str) -> bytes:
    return text.encode("utf-16-le")


class FakeWsl:
    """The wsl command as a stand-in: the user's own Ubuntu running, Liminal-Ubuntu in `state`; Docker inside answering
    the WSL plugin's own look (docker --version, docker info). Every command kept."""

    def __init__(self, state="Stopped", name="Liminal-Ubuntu"):
        self.state, self.name = state, name
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        if args[1] == "--status":
            return 0, u16("Default Distribution: Ubuntu\r\nDefault Version: 2\r\n"), b""
        if args[1:3] == ["--list", "--verbose"]:
            return 0, u16(f"  NAME              STATE           VERSION\r\n* Ubuntu            Running         2\r\n"
                          f"  {self.name}    {self.state}         2\r\n"), b""
        if args[1] == "-d":
            command = args[args.index("--exec") + 1:]
            if command[:2] == ["docker", "--version"]:
                return 0, b"Docker version 29.9.3, build 5c0f1a2\n", b""
            if command[:2] == ["docker", "info"]:
                return 0, b"29.9.3\n", b""
        return 1, b"", b"not answered here"


class Ubuntu(WslDistribution):
    """A WSL plugin as wsl-ubuntu is (the library's WslDistribution: its engine offered as `wsl -d NAME --exec docker`)."""

    name = "wsl-ubuntu"
    title = "WSL Ubuntu"
    about = "a stand-in"
    api = "2.1"
    distribution = "Liminal-Ubuntu"
    family = "apt"


def booted(calls) -> list:
    """The commands that would start a distribution: every `wsl -d NAME ...`."""
    return [c for c in calls if c[:1] == ["wsl"] and "-d" in c]


def plugin(state="Stopped", engine=None, distribution="Liminal-Ubuntu", clock=None):
    """The plugin over Liminal-Ubuntu's engine (the WSL plugin's, through the library's docker.instances; no docker on
    this machine's PATH), the stand-ins it asks."""
    wsl = FakeWsl(state=state, name=distribution)
    ubuntu = type("Distro", (Ubuntu,), {"distribution": distribution})(wsl=Wsl(runner=wsl))
    run = Docker(wsl=engine or FakeEngine())
    p = DockerPlugin(machines=[ubuntu], wsl=Wsl(runner=wsl), runner=run, env={}, **({"clock": clock} if clock else {}))
    return p, run, wsl


def at_local(*when, fmt="%b %d %H:%M") -> str:
    return eng.local_time(datetime(*when, tzinfo=UTC), fmt)


def test_docker_in_a_stopped_distribution_is_never_asked_and_the_plugin_says_why():
    p, run, wsl = plugin("Stopped")
    s = p.status()
    assert s["present"] is True and s["valid"] is False and s["summary"].startswith("no Docker engine answers: wsl-ubuntu: ")
    assert s["why"] == ("no Docker engine can be read: wsl-ubuntu: Liminal-Ubuntu is stopped, and a look never starts it. "
                        "Start the distribution (from its WSL plugin's terminal, say) and Docker in it is read")
    assert run.calls == [] and booted(wsl.calls) == []  # only `wsl --list --verbose`: nothing booted
    engines, containers = s["tables"]
    assert engines["rows"] == [[{"text": "wsl-ubuntu", "sub": "the wsl-ubuntu plugin's"}, "Docker in Liminal-Ubuntu under WSL 2", "–",
                                {"text": "stopped", "sub": "Liminal-Ubuntu is stopped, and a look never starts it"}]]
    assert containers["empty"] == "wsl-ubuntu is not read: Liminal-Ubuntu is stopped, and a look never starts it"
    assert s["forms"] == [] and "options" not in engines  # one engine: nothing to choose
    with pytest.raises(ValueError, match="wsl-ubuntu is not asked now: Liminal-Ubuntu is stopped"):
        p.ask("container", "wsl-ubuntu", "web", "stop")  # a change does not start it either
    with pytest.raises(ValueError, match="not asked now"):
        p.ask("logs", "wsl-ubuntu", "web", 10)
    assert run.calls == [] and booted(wsl.calls) == []
    json.dumps(s)


def test_the_engines_and_the_shown_ones_containers_images_volumes_and_networks():
    p, run, wsl = plugin("Running")
    s = p.status()
    assert s["valid"] is True and s["why"] == "" and "problem" not in s
    assert s["summary"] == "wsl-ubuntu: Docker 29.9.3 · 2 of 3 containers running · 4 images"
    assert all(c[:5] == ["wsl", "-d", "Liminal-Ubuntu", "--exec", "docker"] for c in run.calls)  # through WSL, as the engine says
    assert sorted(c[5] for c in run.calls) == ["images", "network", "ps", "version", "volume"]
    assert (s["engines"], s["shown"]) == ("wsl-ubuntu: running 29.9.3", "wsl-ubuntu (Docker in Liminal-Ubuntu under WSL 2)")
    assert s["engineVersion"] == "29.9.3 · linux/amd64 · client 29.9.3"
    assert (s["containers"], s["images"], s["volumes"], s["networks"]) == ("2 running of 3", "4", "2", "4")
    assert [t["title"] for t in s["tables"]] == ["Docker engines", "Containers", "Images", "Volumes", "Networks"]
    engines, containers, images, volumes, networks = s["tables"]
    assert engines["rows"][0][2:] == [{"text": "29.9.3", "sub": "client 29.9.3 · linux/amd64"}, "running"]
    assert containers["note"] == "on wsl-ubuntu (Docker in Liminal-Ubuntu under WSL 2)"
    assert [c["title"] for c in containers["columns"]] == ["Container", "Image", "State", "Ports", "Created", "Log", "Change", "Remove"]
    mail, web, job = containers["rows"]  # the running first
    assert web[:5] == [{"text": "web", "sub": "3f2a9c1e5b7d"}, "nginx:1.27", {"text": "running", "sub": "Up 2 hours"},
                       "0.0.0.0:8080->80/tcp", {"text": at_local(2026, 11, 8, 7, 10, 44), "sub": "2 hours ago"}]
    assert web[5:] == [{"form": "logs", "title": "Logs", "values": {"name": "web"}, "label": "Read the last lines of web's log"},
                       {"form": "container", "title": "Stop…", "values": {"name": "web", "action": "stop"}, "label": "Stop web"},
                       {"form": "remove", "title": "Remove…", "values": {"name": "web"}, "label": "Remove web"}]
    assert mail[0] == {"text": "mail-example-com", "sub": "9b8a7c6d5e4f · Liminal's service"}
    assert mail[3] == "127.0.0.1:8025->25/tcp, 0.0.0.0:465->465/tcp"  # the IPv6 twin left out
    assert job[2] == {"text": "exited", "sub": "Exited (0) 5 days ago"} and job[3] == "–" and job[6]["title"] == "Start…"
    assert [a.get("form") for a in containers["actions"]] == ["container", "logs", "remove"]
    assert [r[0] for r in images["rows"]] == [{"text": "ghcr.io/docker-mailserver/docker-mailserver:15.0", "sub": "7d6c5b4a3f2e"},
                                              {"text": "nginx:1.27", "sub": "4e1b2c3d4f5a"}, {"text": "python:3.13-slim", "sub": "a1b2c3d4e5f6"},
                                              {"text": "(untagged)", "sub": "9a8b7c6d5e4f"}]
    assert [r[3] for r in images["rows"]] == ["mail-example-com", "web", "old-job", "–"]  # what each was made into
    assert images["rows"][1][1:3] == ["192MB", {"text": "10 days ago", "sub": at_local(2026, 10, 29, 1, 2, 3)}]
    assert images["rows"][3][4]["values"] == {"image": "9a8b7c6d5e4f"} and images["actions"] == [{"form": "pull", "title": "Pull an image…"}]
    assert volumes["rows"] == [[{"text": "maildata", "sub": "/var/lib/docker/volumes/maildata/_data"}, "local", "local", "mail-example-com"],
                               [{"text": "5e9f2c7b1a3d…", "sub": "anonymous"}, "local", "local", "old-job"]]
    assert networks["rows"] == [[{"text": "bridge", "sub": "0d4b6f8a1c3e"}, "bridge", "local", "2", "–"],
                                [{"text": "host", "sub": "1e5c7a9b2d4f"}, "host", "local", "0", "–"],
                                [{"text": "liminal", "sub": "3a7e9c1d4f6b"}, "bridge", "local", "1", "IPv6"],
                                [{"text": "none", "sub": "2f6d8b0c3e5a"}, "null", "local", "0", "–"]]
    forms = {f["id"]: f for f in s["forms"]}
    assert list(forms) == ["container", "remove", "logs", "rmi", "pull"]
    for f in s["forms"]:  # the fields are the hook's arguments, in order; the engine shown fixed in each
        assert [x["name"] for x in f["fields"]] == list(inspect.signature(getattr(p, f["hook"])).parameters)
        assert f["fields"][0] == {"name": "engine", "label": "Engine", "type": "fixed", "value": "wsl-ubuntu"}
    assert [c["value"] for c in forms["container"]["fields"][1]["choices"]] == ["mail-example-com", "web", "old-job"]
    assert forms["remove"]["confirm"]["danger"] is True and forms["remove"]["fields"][2]["type"] == "accept"
    assert forms["rmi"]["confirm"]["danger"] is True and forms["logs"]["confirm"] is False
    assert s["actions"] == [{"hook": "refresh", "args": [], "title": "Read again", "note": "asks every engine again now (what was read is kept 30 s)"}]
    json.dumps(s)


def test_a_container_stopped_started_restarted_and_removed_once_confirmed():
    p, run, wsl = plugin("Running")
    engine = run.engines["wsl"]
    assert p.ask("container", "wsl-ubuntu", "web", "stop") == {"said": "web stopped on wsl-ubuntu", "ok": True,
                                                                "lines": ["now exited: Exited (0) Less than a second ago"]}
    assert ["stop", "-t", "20", "web"] in engine.asked
    assert p.status()["containers"] == "1 running of 3"  # what was read went with the change
    with pytest.raises(ValueError, match="web is not running on wsl-ubuntu"):
        p.ask("container", "wsl-ubuntu", "web", "stop")
    assert p.ask("container", "wsl-ubuntu", "web", "start")["ok"] is True
    with pytest.raises(ValueError, match="web is running already on wsl-ubuntu"):
        p.ask("container", "wsl-ubuntu", "web", "start")
    assert p.ask("container", "wsl-ubuntu", "web", "restart")["said"] == "web restarted on wsl-ubuntu"
    assert ["restart", "-t", "20", "web"] in engine.asked
    with pytest.raises(ValueError, match="started, stopped or restarted, not 'pause'"):
        p.ask("container", "wsl-ubuntu", "web", "pause")
    with pytest.raises(ValueError, match="no container named ghost on wsl-ubuntu"):
        p.ask("container", "wsl-ubuntu", "ghost", "start")
    with pytest.raises(ValueError, match="not a container's name"):
        p.ask("container", "wsl-ubuntu", "--rm", "stop")
    with pytest.raises(ValueError, match="no Docker engine named 'elsewhere' here: wsl-ubuntu"):
        p.ask("container", "elsewhere", "web", "stop")
    with pytest.raises(Refusal) as refused:  # running: the page asks again (its accept field), else nothing is done
        p.ask("remove_container", "wsl-ubuntu", "web", False)
    assert refused.value.accept == "force" and str(refused.value).startswith("web is running on wsl-ubuntu: stop it first")
    assert not any(a[0] == "rm" for a in engine.asked)
    assert p.ask("remove_container", "wsl-ubuntu", "web", True)["said"] == "web removed from wsl-ubuntu"
    assert ["rm", "-f", "web"] in engine.asked
    gone = p.ask("remove_container", "wsl-ubuntu", "old-job", None)
    assert gone["said"] == "old-job removed from wsl-ubuntu" and gone["lines"] == ["it was exited (Exited (0) 5 days ago), made from python:3.13-slim"]
    assert ["rm", "old-job"] in engine.asked and [c["Names"] for c in engine.containers] == ["mail-example-com"]


def test_a_log_read_and_images_pulled_and_removed():
    p, run, wsl = plugin("Running")
    engine = run.engines["wsl"]
    a = p.ask("logs", "wsl-ubuntu", "web", None)
    assert ["logs", "--tail", "100", "--timestamps", "web"] in engine.asked
    assert a["said"] == f"the last 4 lines of web's log on wsl-ubuntu ({at_local(2026, 11, 8, 9, 14, 3)} to {at_local(2026, 11, 8, 9, 20, 12)})"
    t = lambda *hms: at_local(2026, 11, 8, *hms, fmt="%H:%M:%S")  # noqa: E731
    assert a["lines"] == [f"{t(9, 14, 3)} /docker-entrypoint.sh: Configuration complete; ready for start up",
                          f"{t(9, 14, 3)} 2026/11/08 09:14:03 [notice] 1#1: nginx/1.27.2",  # its errors where they were written
                          f'{t(9, 20, 11)} 172.17.0.1 - - [08/Nov/2026:09:20:11 +0000] "GET / HTTP/1.1" 200 615 "-" "curl/8.5.0"',
                          f'{t(9, 20, 12)} 2026/11/08 09:20:12 [error] 29#29: *2 open() "/usr/share/nginx/html/favicon.ico" failed (2: No such file or directory)']
    assert p.ask("logs", "wsl-ubuntu", "web", 2)["lines"] == a["lines"][-2:]
    for wrong in (0, 2001, "many"):
        with pytest.raises(ValueError):
            p.ask("logs", "wsl-ubuntu", "web", wrong)
    pulled = p.ask("pull", "wsl-ubuntu", "nginx:1.28")
    assert pulled == {"said": "nginx:1.28 pulled on wsl-ubuntu", "ok": True,
                      "lines": ["Digest: sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0",
                                "Status: Downloaded newer image for nginx:1.28", "docker.io/library/nginx:1.28"]}
    assert ["pull", "nginx:1.28"] in engine.asked and "nginx:1.28" in [r[0]["text"] for r in p.status()["tables"][2]["rows"]]
    for wrong in ("--help", "nginx latest", "", None):
        with pytest.raises(ValueError, match="not an image's name"):
            p.ask("pull", "wsl-ubuntu", wrong)
    with pytest.raises(Refusal) as used:
        p.ask("remove_image", "wsl-ubuntu", "nginx:1.27", False)
    assert used.value.accept == "force" and str(used.value).startswith("nginx:1.27 is what web was made from on wsl-ubuntu")
    assert not any(a[0] == "rmi" for a in engine.asked)
    removed = p.ask("remove_image", "wsl-ubuntu", "nginx:1.28", None)  # no container was made from it
    assert removed["said"] == "nginx:1.28 removed from wsl-ubuntu" and removed["lines"][0] == "Untagged: nginx:1.28"
    assert ["rmi", "nginx:1.28"] in engine.asked
    assert p.ask("remove_image", "wsl-ubuntu", "python:3.13-slim", True)["ok"] and ["rmi", "-f", "python:3.13-slim"] in engine.asked
    with pytest.raises(ValueError, match="no image redis:7 on wsl-ubuntu"):
        p.ask("remove_image", "wsl-ubuntu", "redis:7")


def test_several_engines_one_shown_and_chosen_on_the_page():
    found = [Instance("local", "this machine", command="docker", source="the docker command"),
             Instance("context:vps", "ssh://liminal@vps.example.net", command="docker", context="vps", source="a docker context"),
             Instance("host", "tcp://10.0.0.5:2376", command="docker", host="tcp://10.0.0.5:2376", source="LIMINAL_DOCKER_HOST")]
    run = Docker(local=FakeEngine(daemon=False), vps=FakeEngine(containers=[], images=[]), host=FakeEngine())
    wsl = FakeWsl()
    p = DockerPlugin(find=lambda: found, runner=run, wsl=Wsl(runner=wsl))
    s = p.status()
    assert wsl.calls == []  # no engine through WSL: WSL is not asked
    engines = s["tables"][0]
    assert [r[0] for r in engines["rows"]] == [{"text": "local", "sub": "the docker command"}, {"text": "context:vps", "sub": "a docker context"},
                                               {"text": "host", "sub": "LIMINAL_DOCKER_HOST"}]
    assert engines["rows"][0][3] == {"text": "not answering", "sub": "its engine is not running (the docker command answers, its daemon does not)"}
    [group] = engines["options"]
    assert group["hook"] == "choose_engine" and group["value"] == "context:vps"  # the first that answers
    assert [c["value"] for c in group["choices"]] == ["local", "context:vps", "host"]
    assert ["docker", "--context", "vps", "version", "--format", "{{json .}}"] in run.calls
    assert ["docker", "-H", "tcp://10.0.0.5:2376", "ps", "-a", "--no-trunc", "--format", "{{json .}}"] not in run.calls  # not shown
    containers, images = s["tables"][1], s["tables"][2]
    assert containers["rows"] == [] and containers["empty"] == "No container on context:vps." and "actions" not in containers
    assert images["empty"] == "No image on context:vps." and [f["id"] for f in s["forms"]] == ["pull"]
    assert s["engines"] == ("local: its engine is not running (the docker command answers, its daemon does not); "
                            "context:vps: running 29.9.3; host: running 29.9.3")
    chosen = p.ask("choose_engine", "host")
    assert chosen["said"] == "showing host's containers, images, volumes and networks" and chosen["ok"]
    s = p.status()
    assert s["shown"] == "host (tcp://10.0.0.5:2376)" and len(s["tables"][1]["rows"]) == 3 and s["tables"][0]["options"][0]["value"] == "host"
    assert ["docker", "-H", "tcp://10.0.0.5:2376", "ps", "-a", "--no-trunc", "--format", "{{json .}}"] in run.calls
    with pytest.raises(ValueError, match="no Docker engine named 'nope' here: local, context:vps, host"):
        p.ask("choose_engine", "nope")
    p.ask("choose_engine", "local")
    s = p.status()
    assert s["valid"] is True and s["problem"] == "local is not read: its engine is not running (the docker command answers, its daemon does not)"
    assert s["tables"][1]["empty"].startswith("local is not read: ") and s["forms"] == []
    p.detach()
    assert p.status()["shown"].startswith("local")  # kept until the platform restarts


def test_no_engine_at_all_is_not_valid_and_says_how_to_have_one():
    p = DockerPlugin(find=lambda: [], runner=Docker(), wsl=Wsl(runner=FakeWsl()))
    s = p.status()
    assert (s["present"], s["valid"], s["why"], s["summary"]) == (False, False, dk.NO_ENGINE, "no Docker engine here")
    assert len(s["tables"]) == 1 and s["tables"][0]["rows"] == [] and s["forms"] == [] and not p.present()
    assert dk.NO_ENGINE == "no Docker engine here: install Docker Desktop, or Docker inside a WSL distribution through the WSL plugins"
    q = DockerPlugin(machines=[], runner=Docker(), wsl=Wsl(runner=FakeWsl()), env={})  # the library's docker.instances itself
    assert q.status()["why"] == dk.NO_ENGINE  # no docker on PATH, no host, no plugin's engine


def test_a_distribution_not_liminals_and_a_plugin_that_fails_are_not_asked():
    p, run, wsl = plugin("Running", distribution="Ubuntu")  # a WSL plugin pointed at the user's own Ubuntu
    s = p.status()
    assert s["valid"] is False and s["tables"][0]["rows"][0][3] == {"text": "not asked", "sub": "Ubuntu is not Liminal's: nothing is asked inside it"}
    assert run.calls == []

    class Failing(Ubuntu):
        name = "wsl-fedora"

        def instances(self):
            raise RuntimeError("wsl is broken")
    q = DockerPlugin(machines=[Failing(wsl=Wsl(runner=FakeWsl()))], runner=Docker(), wsl=Wsl(runner=FakeWsl()), env={})
    s = q.status()
    assert s["tables"][0]["rows"][0][3] == {"text": "not asked", "sub": "wsl-fedora: RuntimeError: wsl is broken"}


def test_what_was_read_is_kept_nothing_runs_on_its_own_and_detached_it_is_forgotten():
    t = [1000.0]
    p, run, wsl = plugin("Running", clock=lambda: t[0])

    class App:
        NAME = "platform"
    before = threading.active_count()
    interface = p.attach(App(), None)
    assert threading.active_count() == before and run.calls == []  # attached: nothing asked yet, no thread of its own
    assert set(interface["hooks"]) == {"present", "status", "choose_engine", "refresh", "container", "remove_container", "logs",
                                       "pull", "remove_image"}
    p.status()
    n = len(run.calls)
    t[0] += 29
    p.status()
    assert len(run.calls) == n and threading.active_count() == before  # kept READ_S: the page's refreshes ask nothing again
    t[0] += 2
    p.status()
    assert len(run.calls) == 2 * n
    refreshed = p.ask("refresh")
    assert refreshed == {"said": "read 1 engine now: 1 answering", "ok": True, "lines": ["wsl-ubuntu: running 29.9.3"]}
    assert len(run.calls) == 3 * n
    p.detach()
    assert p._rt.reading is None and p.app is None and threading.active_count() == before


def test_every_command_runs_windowless_its_output_read_whatever_the_code_page(monkeypatch):
    seen = {}

    def recording(args, **kw):
        seen.update(args=args, **kw)
        return subprocess.CompletedProcess(args, 3, "h\u00e9llo".encode() + b" \xff", u16("There is no distribution with the supplied name."))
    monkeypatch.setattr(subprocess, "run", recording)
    assert eng.run(["docker", "version"], 5) == (3, "h\u00e9llo \ufffd", "There is no distribution with the supplied name.")
    assert seen["stdin"] is subprocess.DEVNULL and seen["capture_output"] and seen["timeout"] == 5 and seen["env"]["WSL_UTF8"] == "1"
    if os.name == "nt":
        assert seen["creationflags"] == 0x08000000  # CREATE_NO_WINDOW: no Windows Terminal window for a console child
    else:
        assert "creationflags" not in seen
    e = eng.Engine.for_instance(Instance("local", "this machine", command="docker"))  # no runner given: the windowless one
    with pytest.raises(DockerError, match="There is no distribution"):
        e.version()
    assert seen["args"][1:] == ["version", "--format", "{{json .}}"] and seen.get("creationflags", 0x08000000) == 0x08000000

    def slow(args, **kw):
        raise subprocess.TimeoutExpired(args, kw["timeout"])
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(DockerError, match="docker ps took more than 7 s"):
        eng.run(["docker", "ps"], 7)

    def missing(args, **kw):
        raise FileNotFoundError(2, "The system cannot find the file specified")
    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(DockerError, match="docker could not run"):
        eng.run(["C:/bin/docker", "ps"], 7)


def test_the_engines_words_and_what_their_listings_say():
    assert eng.wsl_target("wsl -d Liminal-Ubuntu --exec docker") == (True, "Liminal-Ubuntu")
    assert eng.wsl_target("C:/Windows/System32/wsl.exe --distribution Liminal-Fedora -- docker") == (True, "Liminal-Fedora")
    assert eng.wsl_target("wsl docker") == (True, "") and eng.wsl_target("docker") == (False, "") and eng.wsl_target("") == (False, "")
    assert eng.wsl_target("wsl --exec docker -d x") == (True, "")  # after --exec it is docker's own
    assert eng.words(DockerError(NO_DAEMON)) == "its engine is not running (the docker command answers, its daemon does not)"
    assert eng.words(DockerError("<3>WSL (2451) ERROR: CreateProcessCommon:640: execvpe(docker) failed: No such file or directory")) \
        == "Docker is not installed there"
    assert eng.words(DockerError("error during connect: Get \"http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.52/version\": open "
                                 "//./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.")) == "Docker Desktop is not running"
    assert eng.words(DockerError("permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock")) \
        == "permission denied: the user is not in the docker group"
    assert eng.words(DockerError("first\nError response from daemon: something else")) == "Error response from daemon: something else"
    assert eng.ports("0.0.0.0:8080->80/tcp, [::]:8080->80/tcp, [::]:9000->9000/tcp") == "0.0.0.0:8080->80/tcp, [::]:9000->9000/tcp"
    assert eng.short("sha256:4e1b2c3d4f5a6b7c8d9e") == "4e1b2c3d4f5a" and eng.short(None) == ""
    assert eng.created("2026-11-08 07:10:44 +0000 UTC") == at_local(2026, 11, 8, 7, 10, 44)
    assert eng.created("") == "–" and eng.created("yesterday") == "yesterday"
    assert eng.names("a,b") == ["a", "b"] and eng.names(["a"]) == ["a"] and eng.names(None) == []
    assert eng.liminal_service({"Labels": "a=b,liminal=service"}) and not eng.liminal_service({"Labels": "liminal=services"})
    assert eng.image_ref({"Repository": "<none>", "Tag": "<none>", "ID": "sha256:" + "ab" * 32}) == "ab" * 6
    assert eng.text(u16("The")) == "The" and eng.text(b"caf\xc3\xa9") == "caf\u00e9" and eng.text("as is") == "as is"
    assert eng.broken(Instance("wsl-gentoo", "wsl-gentoo: WslError: no", source="wsl-gentoo"))
    assert not eng.broken(Instance("wsl-gentoo", "Docker in Liminal-Gentoo under WSL 2", source="wsl-gentoo"))
    assert eng.log_lines("no stamp here\n", "") == ["no stamp here"] and eng.span("", "") == ""


def test_the_command_line(monkeypatch, capsys):
    p, run, wsl = plugin("Running")
    monkeypatch.setattr(cli, "MACHINE", p)
    assert cli.main(["status"]) == 0 and json.loads(capsys.readouterr().out)["valid"] is True
    assert cli.main(["engines"]) == 0 and capsys.readouterr().out == "wsl-ubuntu: running 29.9.3  (Docker in Liminal-Ubuntu under WSL 2)\n"
    assert cli.main(["containers"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Containers on wsl-ubuntu (Docker in Liminal-Ubuntu under WSL 2)" and len(out) == 4
    assert out[2].startswith("  web (3f2a9c1e5b7d)  nginx:1.27  running (Up 2 hours)  0.0.0.0:8080->80/tcp")
    assert cli.main(["networks", "wsl-ubuntu"]) == 0 and "  liminal (3a7e9c1d4f6b)  bridge  local  1  IPv6" in capsys.readouterr().out
    assert cli.main(["logs", "wsl-ubuntu", "web", "1"]) == 0 and capsys.readouterr().out.startswith("the last 1 line of web's log")
    assert cli.main(["stop", "wsl-ubuntu", "web"]) == 0 and capsys.readouterr().out.startswith("web stopped on wsl-ubuntu")
    assert cli.main(["remove", "wsl-ubuntu", "mail-example-com"]) == 1
    assert capsys.readouterr().err.strip().endswith("(--force does it anyway)")
    assert cli.main(["remove", "wsl-ubuntu", "mail-example-com", "--force"]) == 0 and "removed" in capsys.readouterr().out
    assert cli.main(["pull", "wsl-ubuntu", "nginx:1.28"]) == 0 and cli.main(["rmi", "wsl-ubuntu", "nginx:1.28"]) == 0
    capsys.readouterr()
    assert cli.main(["start", "wsl-ubuntu", "ghost"]) == 1 and "refused: no container named ghost" in capsys.readouterr().err
    assert cli.main(["dance"]) == 2 and cli.main(["logs", "wsl-ubuntu"]) == 2
    assert capsys.readouterr().err.count("python -m plugin_platform_docker status | engines") == 2
    q, run, wsl = plugin("Stopped")
    monkeypatch.setattr(cli, "MACHINE", q)
    assert cli.main(["status"]) == 1 and cli.main(["engines"]) == 1 and cli.main(["images"]) == 1
    capsys.readouterr()
    assert cli.main(["stop", "wsl-ubuntu", "web"]) == 1 and "refused: wsl-ubuntu is not asked now" in capsys.readouterr().err
    assert run.calls == [] and booted(wsl.calls) == []
