"""0.4.0: the one "run a service" interface (liminal-libs 1.93.0's ContainerHost) on Docker inside Liminal-Ubuntu, its
first engine (decision 4). The plugin is attached to a real apps.App beside the library's stand-in firewall, a stand-in
WSL plugin that holds the distribution, and stand-in service plugins, so the asker's gates are the real ones. Every
docker command goes through the plugin's own runner to the library's FakeDocker; WSL's own command is FakeWsl's: nothing
runs, nothing is pulled, no port is opened, no distribution is booted."""
from __future__ import annotations

import json

import pytest

from liminal_libs.apps import App, asking
from liminal_libs.apps.asking import AskRefused
from liminal_libs.instances import Refusal
from liminal_libs.machines import standins
from liminal_libs.machines.standins import FakeDocker, ServiceOwner, StandInNetworkHost, StandInWsl
from liminal_libs.machines.wsl import Wsl
from plugin_platform_docker import DockerPlugin
from plugin_platform_docker import Refusal as DockerRefusal
from test_plugin import FakeWsl, Ubuntu, booted

DIG = "sha256:" + "a" * 64
SECRET = "canary-Qz71-never-shown"


class Frame(App):
    NAME = "frame"

    def __init__(self, login):
        super().__init__(log=lambda m: None, login=login)
        self.off: set[str] = set()

    def disabled(self):
        return set(self.off)

    def known_plugins(self):
        return list(self._plugins.values())


def spec(owner="jenkins", name="ci", host=8080, lan=True, secrets=()):
    return {"owner": owner, "name": name, "title": owner.capitalize(), "system": "linux", "parts": [{
        "name": "controller",
        "image": {"ref": "docker.io/jenkins/jenkins:2.528.2-lts-jdk21", "digest": DIG, "system": "linux",
                  "platforms": ["linux/amd64"], "size": 300_000_000, "licence": "MIT"},
        "ports": [{"name": "web", "container": 8080, "host": host, "lan": lan}],
        "volumes": [{"name": "home", "path": "/var/jenkins_home", "holds": "its jobs and history", "owner": 1000}],
        "env": {"JAVA_OPTS": "-Dhudson.model.UsageStatistics.disabled=true"}, "secrets": list(secrets),
        "readable": [{"name": "unlock", "volume": "home", "path": "secrets/initialAdminPassword"}],
        "memory": 2 << 30, "health": {"port": "web", "path": "/login", "ready_s": 30}}]}


class World:
    def __init__(self, tmp_path, state="Running", holds=True):
        self.fake = FakeDocker(version="29.9.3")
        self.wsl_cmd = FakeWsl(state=state)
        ubuntu = Ubuntu(wsl=Wsl(runner=self.wsl_cmd))
        self.login = standins.login({"JENKINS_ADMIN_PASSWORD": SECRET})
        out = standins.Outside(sleep=lambda s: None, health=lambda h, p, path: True, platform="windows::TEST",
                               holders=lambda port: [], folder=tmp_path)
        self.docker = DockerPlugin(machines=[ubuntu], wsl=Wsl(runner=self.wsl_cmd), runner=self.fake,
                                   streamer=self.fake.stream, service_runner=self.fake, env={}, outside=out)
        self.app = Frame(self.login)
        self.firewall = StandInNetworkHost()
        self.holder = StandInWsl()
        object.__setattr__(self.holder, "name", "wsl-ubuntu")  # the WSL plugin that offers the engine holds it
        self.jenkins = ServiceOwner("jenkins", host="docker")
        self.gocd = ServiceOwner("gocd", host="docker")
        for p in (self.docker, self.firewall, *([self.holder] if holds else []), self.jenkins, self.gocd):
            self.app.attach(p)

    def page(self, plugin, hook, *args):
        with asking.asking(asking.PAGE):
            return self.app.ask(plugin, hook, *args)

    def grant(self, plugin="jenkins"):
        self.page("docker", "grant_service", plugin, "wsl-ubuntu")
        if "docker" not in self.firewall.network_grants():
            self.page("standin-firewall", "grant_network", "docker")

    def wait(self, work, who=None):
        w = self.docker._svc.works.get(work)
        w.thread.join(20)
        assert not w.thread.is_alive()
        return (who or self.jenkins).call("service_work", work, 0)

    def carry(self, action, spec_=None, options=None, target="", who=None):
        who = who or self.jenkins
        sid = f"{who.name}/ci"
        plan = who.call("service_plan", action, sid, spec_, target, options or {})
        for a in plan["approve"]:
            words = self.page(a["plugin"], "plan_words", a["plan"])
            needed = {x["name"] for x in words["accepts"]}
            order = standins._ACCEPT_ORDER[a["plugin"] == "docker"]
            self.page(a["plugin"], "approve_plan", a["plan"], *[k in needed for k in order])
        return plan, self.wait(who.call("apply_plan", plan["plan"])["work"], who=who)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_docker_inside_liminal_ubuntu_is_its_target(world):
    got = world.jenkins.call("hosting", "jenkins", {"linux": spec()})
    t = got["targets"][0]
    assert t["id"] == "wsl-ubuntu" and t["state"] == "ready" and t["wsl"] == "Liminal-Ubuntu"
    assert t["stack"] == "wsl" and t["path"] == "wsl-nat" and t["firewall"] == "windows"
    assert t["wsl_plugin"] == "wsl-ubuntu" and t["fit"]["takes"] == "" and t["version"] == "29.9.3"
    assert "Liminal-Ubuntu's virtual disk" in t["where_data"]


def test_an_install_runs_every_command_through_wsl_exactly(world):
    world.grant()
    plan, end = world.carry("install", spec(secrets=[{"variable": "JENKINS_ADMIN_PASSWORD", "env": "ADMIN_PASSWORD"}]),
                            target="wsl-ubuntu")
    assert end["ok"], end
    service = [c for c in world.fake.calls if c["key"] not in ("version", "ps", "images", "volume ls", "network ls")
               or "--filter" in c["argv"]]
    assert all(c["argv"][:5] == ["wsl", "-d", "Liminal-Ubuntu", "--exec", "docker"] for c in service)
    create = next(c for c in world.fake.calls if c["key"] == "create")
    line = " ".join(create["argv"])
    assert "--restart no" in line and "-p 8080:8080/tcp" in line and f"--memory {2 << 30}" in line
    assert "-e ADMIN_PASSWORD" in line and SECRET not in line
    assert create["env"] == {"ADMIN_PASSWORD": SECRET, "WSLENV": "ADMIN_PASSWORD/u"}
    assert "-v liminal-jenkins-ci-home:/var/jenkins_home" in line and line.endswith("@" + DIG)
    assert "trusted_host_interfaces=eth0" in " ".join(world.fake.argv_of("network create")[0])
    assert world.holder.asked == [("hold", "Liminal-Ubuntu")]
    # wsl itself: its list, and the WSL plugin's own look inside the running distribution (never one that is stopped)
    assert all(c[:5] == ["wsl", "-d", "Liminal-Ubuntu", "--exec", "docker"] for c in booted(world.wsl_cmd.calls))
    said = json.dumps([plan, end, world.page("docker", "status")])
    assert SECRET not in said


def test_a_stopped_distribution_runs_no_command_at_all(tmp_path):
    w = World(tmp_path, state="Stopped")
    w.grant()
    with pytest.raises(Refusal, match="Nothing here starts it"):
        w.jenkins.call("service_plan", "install", "jenkins/ci", spec(), "wsl-ubuntu", {})
    assert w.fake.calls == [] and booted(w.wsl_cmd.calls) == []


def test_its_own_remove_refuses_a_services_container(world):
    world.grant()
    world.carry("install", spec(), target="wsl-ubuntu")
    with pytest.raises(DockerRefusal, match="remove it on jenkins's page"):
        world.docker.remove_container("wsl-ubuntu", "liminal-jenkins-ci-controller", True)
    assert "liminal-jenkins-ci-controller" in world.fake.containers and world.fake.argv_of("rm") == []


def test_its_own_changes_are_its_pages_alone(world):
    for hook, args in (("container", ("wsl-ubuntu", "x", "stop")), ("remove_container", ("wsl-ubuntu", "x")),
                       ("pull", ("wsl-ubuntu", "nginx:1.27")), ("remove_image", ("wsl-ubuntu", "nginx")),
                       ("choose_engine", ("wsl-ubuntu",))):
        with pytest.raises(AskRefused):
            world.jenkins.call(hook, *args)


def test_without_its_wsl_plugins_hold_the_lifecycle_differs(tmp_path):
    w = World(tmp_path, holds=False)
    w.grant()
    plan = w.jenkins.call("service_plan", "install", "jenkins/ci", spec(), "wsl-ubuntu", {})
    assert "accept_differs" in [a["name"] for a in plan["accepts"]]


def test_turning_it_off_stops_its_page_services(world):
    world.grant()
    world.carry("install", spec(), target="wsl-ubuntu")
    world.app.off.add("docker")
    world.app.detach("docker")
    assert world.fake.containers["liminal-jenkins-ci-controller"]["state"] == "exited"
    assert world.fake.argv_of("rm") == [] and world.fake.argv_of("volume rm") == []


def test_the_page_lists_services_plans_plugins_and_kept_data(world):
    s = world.page("docker", "status")
    titles = [t["title"] for t in s["tables"]]
    assert titles[-4:] == ["Liminal's services", "Waiting for your answer", "Service plugins", "Kept data"]
    assert {"approve", "decline", "grant", "revoke", "forget"} <= {f["id"] for f in s["forms"]}
    approve = next(f for f in s["forms"] if f["id"] == "approve")
    assert [x["name"] for x in approve["fields"]] == ["plan", "accept_lan", "accept_kept_secret", "accept_differs",
                                                      "accept_boot", "accept_no_backup", "accept_data"]


def test_the_conformance_sequence_runs_on_docker_in_wsl(world):
    world.grant()

    def wait(work):
        return world.wait(work)
    done = standins.conformance(world.jenkins, world.page, spec(), "wsl-ubuntu", wait)
    assert done[-1] == "conformance"
    assert world.fake.containers == {} and world.fake.volumes == {} and world.fake.networks == {}


def service_flow(tmp_path) -> FakeDocker:
    """Every service command the plugin runs (for its API card's test): the conformance sequence, a log read, a file."""
    w = World(tmp_path)
    w.grant()
    w.carry("install", spec(), target="wsl-ubuntu")
    w.fake.volumes["liminal-jenkins-ci-home"]["files"]["secrets/initialAdminPassword"] = b"x"
    w.jenkins.call("hosted_file", "jenkins/ci", "controller", "unlock")
    w.carry("stop")
    w.jenkins.call("hosted_file", "jenkins/ci", "controller", "unlock")
    w.jenkins.call("hosted_logs", "jenkins/ci")
    w.carry("start")
    w.carry("update", {**spec(), "parts": [{**spec()["parts"][0], "image": {**spec()["parts"][0]["image"],
                                                                          "digest": "sha256:" + "b" * 64}}]})
    w.carry("rollback", options={"choice": "backup"})
    w.carry("remove")
    w.carry("delete_data", options={"backups": "delete"})
    w.jenkins.call("segments")
    return w.fake


def test_an_engine_on_another_machine_never_hosts_a_service(tmp_path):
    from liminal_libs.docker import Instance

    fake = FakeDocker(version="29.9.3")
    p = DockerPlugin(find=lambda: [Instance("context:vps", "ssh://me@vps.example", context="vps", source="a docker context")],
                     runner=fake, streamer=fake.stream, service_runner=fake, wsl=Wsl(runner=FakeWsl()), env={},
                     outside=standins.Outside(sleep=lambda s: None, platform="windows::TEST", folder=tmp_path))
    t = p.runtime_targets()[0]
    assert (t.here, t.state) == (False, "not here") and "stays on this machine" in t.why


def test_a_windows_engine_is_left_to_the_windows_containers_plugin(tmp_path):
    from liminal_libs.docker import Instance

    fake = FakeDocker(version="29.9.3")
    fake._answer_version = fake._answer

    def windows(key, args, stdin, env, out):
        if key == "version":
            return 0, json.dumps({"Client": {"Version": "29"}, "Server": {"Version": "29", "Os": "windows", "Arch": "x86_64"}}), ""
        return fake._answer_version(key, args, stdin, env, out)
    fake._answer = windows
    p = DockerPlugin(find=lambda: [Instance("local", "this machine", source="the docker command")], runner=fake,
                     streamer=fake.stream, service_runner=fake, wsl=Wsl(runner=FakeWsl()), env={},
                     outside=standins.Outside(sleep=lambda s: None, platform="windows::TEST", folder=tmp_path))
    t = p.runtime_targets()[0]
    assert t.state == "not here" and "Windows containers plugin" in t.why


def test_a_plain_stand_in_runner_never_runs_a_service_command_for_real(tmp_path):
    w = World(tmp_path)
    w.docker._service_runner = None
    with pytest.raises(DockerRefusal, match="takes no standard input"):
        w.docker._service_command(["docker", "create"], 5, env={"X": "y"})


def test_a_plan_says_where_the_engine_keeps_its_data_in_its_own_word(world):
    # 0.4.1: docker info's DockerRootDir (liminal-libs 1.95.0's data_root, read_root on), beside the target's words
    world.grant()
    world.fake.root = "/mnt/wsl-data/docker"
    plan = world.jenkins.call("service_plan", "install", "jenkins/ci", spec(), "wsl-ubuntu", {})
    assert "virtual disk (unregistering Liminal-Ubuntu deletes it) (/mnt/wsl-data/docker)." in plan["words"]
    info = world.fake.argv_of("info")
    assert info and all(a[:5] == ["wsl", "-d", "Liminal-Ubuntu", "--exec", "docker"] for a in info)
    assert set(world.fake.changes()) <= {"images"}  # a plan changes nothing (its listing of images is a read)
