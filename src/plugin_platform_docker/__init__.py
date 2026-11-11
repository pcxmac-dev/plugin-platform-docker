"""Docker for Liminal (the user, 2026-11-08: "and then i need a kubernetes and docker plugin for platform"; earlier:
"basically the platform is the interface for the software/hardware which facilitates the liminal framework"): every
Docker engine the library knows (liminal_libs.docker.instances: this machine's docker command and its contexts,
LIMINAL_DOCKER_HOST, and Docker inside Liminal's WSL distributions, offered by the WSL plugins), each one's version and
whether it runs; the containers, images, volumes and networks of the engine chosen on the platform's page; and what the
page changes once confirmed: a container started, stopped, restarted or removed, an image pulled or removed, a
container's last log lines read.

An engine reached through WSL (`wsl -d Liminal-Ubuntu --exec docker`) is asked only while WSL lists its distribution
running: a `wsl -d` boots a stopped one, and a look never starts it (the WSL plugins' rule, liminal-libs 1.28.0); one a
WSL plugin offers in a distribution that is not Liminal's own is not asked at all. Nothing runs on its own: the plugin
reads when the platform asks (what it read kept READ_S, so the page's refreshes do not ask every engine again; a change
reads again at once), holds no process and no thread between asks, and forgets what it read when detached.

    python -m plugin_platform_docker status | engines | containers|images|volumes|networks [ENGINE]
                                    | logs ENGINE NAME [LINES] | start|stop|restart ENGINE NAME
                                    | remove ENGINE NAME [--force] | pull ENGINE IMAGE | rmi ENGINE IMAGE [--force]
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from liminal_libs import docker
from liminal_libs.apps import EnvironmentLogin
from liminal_libs.docker import DockerError, Instance
from liminal_libs.machines.plugin import MachinePlugin, liminal_scoped
from liminal_libs.machines.wsl import Wsl
from liminal_libs.sources.keys import KeyVar

from .catalog import PICKS
from .engines import (STOP_S, Engine, anonymous, broken, created, image_ref, liminal_service, local_time, names, ports,
                      short, span, users_of, words, wsl_target)
from .search import Outcome, Searcher, where_choices
from .sources import SOURCES, Http, canonical, pull_ref, registry_of
from .sources import shown as shown_ref

__version__ = "0.2.0"
WEBSITE_VAR = "DOCKER_HUB_WEBSITE_SEARCH"  # the user's setting: Docker Hub's website search too (undocumented; off)
KEYS = (KeyVar(WEBSITE_VAR, label="Docker Hub's website search", secret=False,
               hint=("optional: on to also ask Docker Hub's website search (undocumented: its ranking, badges and pull counts "
                     "are the best, but Docker's terms allow automated access only through documented APIs; off unless set)")),)
FOUND_ROWS = 25  # a search's results shown
DESCRIPTION_CHARS = 220  # a result's description in its row (Details gives it whole)
READ_S = 30.0  # what was read is kept this long: the platform's page asks every few seconds; a change reads again at once
LOG_LINES = 100  # a container's last lines read unless more are asked
MAX_LOG_LINES = 2000
ROWS = 200  # a table's rows at most
NO_ENGINE = "no Docker engine here: install Docker Desktop, or Docker inside a WSL distribution through the WSL plugins"
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")  # a container's name (or its id)
IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")  # an image's reference: [registry/]name[:tag][@digest], or its id
ACTIONS = {  # a container's change: its title, what it is said as done, the state it leaves
    "start": ("Start", "started", "running"),
    "stop": ("Stop", "stopped", "exited"),
    "restart": ("Restart", "restarted", "running"),
}
UP = ("running", "paused", "restarting")  # a container in one of these is stopped before it is removed


class Refusal(ValueError):
    """A change not made, and why: nothing was asked of the engine. `accept`: the argument that, set, makes it anyway
    (force: a running container removed, an image a container was made from removed); the platform's page asks it as a
    second, explicit confirmation."""

    def __init__(self, message: str, accept: str | None = None):
        super().__init__(message)
        self.accept = accept


@dataclass(frozen=True)
class Seen:
    """An engine as last read: asked or not (an engine in a stopped WSL distribution is not), answering, its versions
    ({client, engine, os, arch}), why it does not answer or was not asked, its WSL distribution when reached through WSL,
    and whether it waits for that distribution to run."""

    instance: Instance
    asked: bool
    answering: bool
    version: dict = field(default_factory=dict)
    why: str = ""
    distribution: str = ""
    stopped: bool = False

    @property
    def name(self) -> str:
        return self.instance.name

    @property
    def state(self) -> str:
        return "running" if self.answering else "stopped" if self.stopped else "not answering" if self.asked else "not asked"

    def line(self) -> str:
        """The engine in one line, as the facts and the command line say it."""
        if self.answering:
            return f"{self.name}: running {self.version.get('engine') or ''}".rstrip()
        return f"{self.name}: {self.why}"


@dataclass
class Listing:
    """The shown engine's containers, images, volumes and networks as read (None: not read), and why one was not."""

    containers: list | None = None
    images: list | None = None
    volumes: list | None = None
    networks: list | None = None
    problems: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Reading:
    """One read of the engines: when (monotonic, for keeping it; the wall's, for the page), each engine, the one shown
    and its listings, and the choice it was read for."""

    at: float
    when: float
    engines: tuple
    shown: str
    listing: Listing | None
    choice: str | None

    def engine(self, name: str) -> Seen | None:
        return next((e for e in self.engines if e.name == name), None)


class _Runtime:
    """What the plugin keeps while it lives, shared by its copies (the registry hands out a shallow one): the last
    reading and the engine chosen on the page (kept until the platform restarts)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reading_lock = threading.Lock()  # one read at a time: a second asker waits, then takes it
        self.reading: Reading | None = None
        self.choice: str | None = None
        self.searching = threading.Lock()  # one image search at a time (0.2.0)
        self.searcher: Searcher | None = None  # its requests' turns and cache, made at the first search
        self.found: Outcome | None = None  # the last search's results, until the next, Clear, or the plugin detached


def cell(text, sub=None):
    return {"text": text, "sub": sub} if sub else text


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def clock(seconds: float) -> str:
    if not seconds:
        return "–"
    return local_time(datetime.fromtimestamp(seconds, timezone.utc))


def yes(value) -> bool:
    """An accepting argument: the page's true, the command line's --force."""
    return value is True or str(value).strip().lower() in ("true", "yes", "1", "on")


def first_name(row: dict) -> str:
    return (names(row.get("Names")) or [short(row.get("ID"))])[0]


def is_up(row: dict) -> bool:
    return str(row.get("State") or "") in UP


def image_order(row: dict) -> tuple:
    """Images by their reference, the untagged after them."""
    ref = image_ref(row)
    return ref == short(row.get("ID")), ref


def _each(fn, items) -> list:
    """`fn` over `items` in order, at once (an engine over SSH or in WSL takes its time: the others do not wait on it);
    the threads end with the call."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(items), 8), thread_name_prefix="docker-read") as pool:
        return list(pool.map(fn, items))


class DockerPlugin(MachinePlugin):
    """Docker's engines for the platform: present when any engine is known, valid when one answers."""

    name = "docker"
    title = "Docker"
    about = ("Every Docker engine here (this machine's, its contexts, a host, Docker inside Liminal's WSL distributions): "
             "each one's version and state, its containers, images, volumes and networks; a container started, stopped, "
             "restarted or removed, an image pulled or removed, once confirmed; an image for anything found on Docker Hub "
             "(through a running engine), Quay and Artifact Hub, described, and pulled with its progress shown")
    api = "2.1"
    order = 705
    ICON = "docker"  # Docker's whale with its containers (liminal-libs 1.33.0's icons.js)
    HOOKS = (*MachinePlugin.HOOKS, "choose_engine", "refresh", "container", "remove_container", "logs", "pull", "remove_image",
             "search", "details", "clear_search")
    JOB_HOOKS = ("pull",)  # hooks the platform may run as a job, their lines followed on the page (liminal-platform 0.19.0)
    keys = KEYS  # its settings, kept through the platform's login (the website search's switch)

    def __init__(self, machines=None, find=None, runner=None, wsl=None, env=None, clock=None, wall=None, http=None, streamer=None):
        self._given = machines  # the machine plugins whose engines count (a test's); else the platform's enabled ones
        self._find = find  # () -> the engines (docker.Instance): docker.instances over those plugins unless given
        self._runner = runner  # (args, timeout) -> (code, out, err): engines.run (windowless) unless given
        self._wsl = wsl  # the wsl command, for whether a distribution runs (a test's stand-in); Wsl() unless given
        self._env = env  # the variables docker.instances reads (LIMINAL_DOCKER_*): this process's unless given
        self._clock = clock or time.monotonic
        self._wall = wall or time.time
        self._http = http  # the registries' requests (sources.Http; a test's stand-in opener inside): made at the first search
        self._streamer = streamer  # (args, timeout, line) -> (code, errors): engines.stream (a pull's lines) unless given
        self._rt = _Runtime()

    # -- the engines ---------------------------------------------------------------------------------------
    def _machines(self) -> list:
        """The machine plugins whose engines count: given (a test's), else the platform's (those it has not disabled:
        it asks a disabled one nothing), else the registry's; never this one."""
        if self._given is not None:
            return [m for m in self._given if getattr(m, "name", "") != self.name]
        app = self.app
        try:
            if app is not None and callable(getattr(app, "machines", None)):
                off = app.disabled() if callable(getattr(app, "disabled", None)) else set()
                return [m for n, m in app.machines().items() if n not in off and n != self.name]
            from liminal_libs.machines import machines

            return [m for n, m in machines().items() if n != self.name]
        except Exception:  # noqa: BLE001 - no registry, no platform: no plugin's engines
            return []

    def _instances(self) -> list[Instance]:
        if self._find is not None:
            return list(self._find())
        return docker.instances(machines=self._machines(), env=self._env)

    def _states(self) -> dict:
        """WSL's distributions by name (lowercase) as `wsl --list --verbose` lists them: it starts none."""
        w = self._wsl if self._wsl is not None else Wsl()
        return {d.name.lower(): d for d in w.distributions()} if w.here else {}

    def _plugins(self) -> set[str]:
        return {str(getattr(m, "name", "")) for m in self._machines()}

    def _gate(self, i: Instance, states: dict, plugins: set[str]) -> tuple[str, str, bool]:
        """Why an engine is not asked now ("" when it may be), its WSL distribution ("" when it is not reached through
        WSL) and whether it waits for that distribution to run: one in a stopped distribution is not asked (a look never
        starts it), nor one a WSL plugin offers in a distribution that is not Liminal's own."""
        if broken(i):
            return i.where, "", False
        through, named = wsl_target(i.command)
        if not through:
            return "", "", False
        d = states.get(named.lower()) if named else next((x for x in states.values() if x.default), None)
        if d is None:
            label = named or "WSL's default distribution"
            return f"{label} is not installed in WSL", named, False
        if i.source in plugins and not liminal_scoped(d.name):
            return f"{d.name} is not Liminal's: nothing is asked inside it", d.name, False
        if str(d.state).lower() != "running":
            return f"{d.name} is {str(d.state).lower()}, and a look never starts it", d.name, True
        return "", d.name, False

    def _engine(self, i: Instance) -> Engine:
        engine = Engine.for_instance(i, runner=self._runner)
        if self._streamer is not None:
            engine._stream = self._streamer
        return engine

    def _probe(self, i: Instance, states: dict, plugins: set[str]) -> Seen:
        why, distribution, stopped = self._gate(i, states, plugins)
        if why:
            return Seen(i, asked=False, answering=False, why=why, distribution=distribution, stopped=stopped)
        try:
            version = self._engine(i).version()
        except (DockerError, ValueError) as e:
            return Seen(i, asked=True, answering=False, why=words(e), distribution=distribution)
        return Seen(i, asked=True, answering=True, version=version, distribution=distribution)

    def _list(self, seen: Seen) -> Listing:
        """The shown engine's four listings, read at once (each its own Engine: one command each)."""
        def one(kind: str):
            try:
                return kind, self._engine(seen.instance).listing(kind), ""
            except (DockerError, ValueError) as e:
                return kind, None, words(e)
        out = Listing()
        for kind, rows, why in _each(one, ("containers", "images", "volumes", "networks")):
            setattr(out, kind, rows)
            if why:
                out.problems[kind] = why
        return out

    def _read(self, fresh: bool = False) -> Reading:
        """The engines and the shown one's listings, kept READ_S for the choice they were read for (`fresh`: read now)."""
        with self._rt.reading_lock:
            with self._rt.lock:
                kept, choice = self._rt.reading, self._rt.choice
            if kept is not None and not fresh and kept.choice == choice and self._clock() - kept.at < READ_S:
                return kept
            found = self._instances()
            plugins = self._plugins()
            states = self._states() if any(wsl_target(i.command)[0] for i in found) else {}
            seen = tuple(_each(lambda i: self._probe(i, states, plugins), found))
            shown = (next((e for e in seen if e.name == choice), None) or next((e for e in seen if e.answering), None)
                     or (seen[0] if seen else None))
            listing = self._list(shown) if shown is not None and shown.answering else None
            reading = Reading(self._clock(), self._wall(), seen, shown.name if shown else "", listing, choice)
            with self._rt.lock:
                self._rt.reading = reading
            return reading

    def _forget(self) -> None:
        with self._rt.lock:
            self._rt.reading = None

    def detach(self) -> None:
        """Detached (the platform ending, the plugin turned off): what it read goes, the last search's results and what
        the registries answered too; nothing of its own was running."""
        self._forget()
        with self._rt.lock:
            self._rt.found = None
            searcher, self._rt.searcher = self._rt.searcher, None
        if searcher is not None:
            searcher.http.forget()
        super().detach()

    # -- the hooks -----------------------------------------------------------------------------------------
    def present(self) -> bool:
        """Whether any Docker engine is known here (answering or not)."""
        with self._rt.lock:
            kept = self._rt.reading
        if kept is not None and self._clock() - kept.at < READ_S:
            return bool(kept.engines)
        try:
            return bool(self._instances())
        except Exception:  # noqa: BLE001 - one that cannot say is not there
            return False

    def engines(self) -> list[Seen]:
        """The engines as read (kept READ_S)."""
        return list(self._read().engines)

    def status(self) -> dict:
        r = self._read()
        shown = r.engine(r.shown)
        answering = [e for e in r.engines if e.answering]
        out: dict = {"present": bool(r.engines), "summary": self._summary(r, shown), "valid": bool(answering),
                     "why": "" if answering else self._why(r)}
        out.update(self._facts(r, shown))
        with self._rt.lock:
            found = self._rt.found
        puller = self._puller(r)
        out["tables"] = [self._found_table(found, puller)] + self._tables(r, shown)
        engine_forms = self._forms(shown, r.listing) if shown is not None and shown.answering and r.listing else []
        if puller is not None and not any(f["id"] == "pull" for f in engine_forms):  # the engine shown is not the one answering
            engine_forms.append(self._pull_form(puller.name))
        out["forms"] = self._search_forms(found, puller) + engine_forms
        out["actions"] = [{"hook": "refresh", "args": [], "title": "Read again",
                           "note": f"asks every engine again now (what was read is kept {READ_S:g} s)"}]
        trouble = [f"{shown.name}'s {kind} could not be read: {why}" for kind, why in (r.listing.problems.items() if r.listing else ())]
        if answering and shown is not None and not shown.answering:
            trouble.append(f"{shown.name} is not read: {shown.why}")
        if trouble:
            out["problem"] = "; ".join(trouble)
        return out

    def _summary(self, r: Reading, shown: Seen | None) -> str:
        if not r.engines:
            return "no Docker engine here"
        more = f" · {plural(len(r.engines), 'engine')}" if len(r.engines) > 1 else ""
        if shown is None or not shown.answering:
            first = next((e for e in r.engines if e.answering), None)
            if first is None:
                return f"no Docker engine answers: {r.engines[0].line()}"
            return f"{first.name}: Docker {first.version.get('engine', '')}{more}"
        said = f"{shown.name}: Docker {shown.version.get('engine', '')}"
        rows = r.listing.containers if r.listing else None
        if rows is not None:
            said += f" · {sum(1 for c in rows if is_up(c))} of {plural(len(rows), 'container')} running"
        if r.listing and r.listing.images is not None:
            said += f" · {plural(len(r.listing.images), 'image')}"
        return said + more

    @staticmethod
    def _why(r: Reading) -> str:
        if not r.engines:
            return NO_ENGINE
        said = "no Docker engine can be read: " + "; ".join(e.line() for e in r.engines[:4])
        if any(e.stopped for e in r.engines):
            said += ". Start the distribution (from its WSL plugin's terminal, say) and Docker in it is read"
        return said

    def _facts(self, r: Reading, shown: Seen | None) -> dict:
        out: dict = {"engines": "; ".join(e.line() for e in r.engines) or "none"}
        if shown is not None:
            out["shown"] = f"{shown.name} ({shown.instance.where})"
            if shown.answering:
                v = shown.version
                out["engineVersion"] = " · ".join(x for x in (v.get("engine", ""), f"{v['os']}/{v.get('arch', '')}" if v.get("os") else "",
                                                               f"client {v['client']}" if v.get("client") else "") if x)
            listing = r.listing
            if listing is not None:
                if listing.containers is not None:
                    out["containers"] = f"{sum(1 for c in listing.containers if is_up(c))} running of {len(listing.containers)}"
                for kind in ("images", "volumes", "networks"):
                    rows = getattr(listing, kind)
                    if rows is not None:
                        out[kind] = str(len(rows))
        out["readAt"] = f"{clock(r.when)} (kept {READ_S:g} s; Read again asks now)"
        return out

    # -- what the platform's page draws: the tables and the forms -----------------------------------------------
    def _tables(self, r: Reading, shown: Seen | None) -> list[dict]:
        out = [self._engines_table(r, shown)]
        if shown is None:
            return out
        on = f"on {shown.name} ({shown.instance.where})"
        listing = r.listing
        if not shown.answering or listing is None:
            out.append({"title": "Containers", "note": on, "columns": [{"title": "Container"}], "rows": [],
                        "empty": f"{shown.name} is not read: {shown.why}"})
            return out
        containers = listing.containers or []
        out.append(self._containers_table(shown, containers, listing.problems.get("containers"), on))
        out.append(self._images_table(shown, listing.images, containers, listing.problems.get("images"), on))
        out.append(self._volumes_table(listing.volumes, containers, listing.problems.get("volumes"), on))
        out.append(self._networks_table(listing.networks, containers, listing.problems.get("networks"), on))
        return out

    @staticmethod
    def _engines_table(r: Reading, shown: Seen | None) -> dict:
        rows = []
        for e in r.engines:
            v = e.version
            sub = " · ".join(x for x in (f"client {v['client']}" if v.get("client") else "", f"{v['os']}/{v.get('arch', '')}" if v.get("os") else "") if x)
            source = e.instance.source if e.instance.source != e.name else f"the {e.name} plugin's"
            rows.append([cell(e.name, source or None), e.instance.where,
                         cell(v.get("engine") or "–", sub or None), cell(e.state, e.why or None)])
        table = {"title": "Docker engines",
                 "note": ("This machine's docker command and its contexts, LIMINAL_DOCKER_HOST, and Docker inside Liminal's WSL "
                          "distributions (asked only while WSL lists the distribution running: a look never starts it)."),
                 "columns": [{"title": "Engine"}, {"title": "Where"}, {"title": "Version"}, {"title": "State"}],
                 "rows": rows, "empty": NO_ENGINE[0].upper() + NO_ENGINE[1:] + "."}
        if len(r.engines) > 1 and shown is not None:
            table["options"] = [{"title": "Shown below", "hook": "choose_engine", "value": shown.name,
                                 "choices": [{"value": e.name, "title": e.name, "note": f"{e.state} · {e.instance.where}"} for e in r.engines]}]
        return table

    @staticmethod
    def _capped(rows: list, note: str) -> tuple[list, str]:
        return (rows[:ROWS], f"{note} · the first {ROWS} of {len(rows):,}") if len(rows) > ROWS else (rows, note)

    def _containers_table(self, shown: Seen, containers: list, problem: str | None, on: str) -> dict:
        ordered = sorted(containers, key=lambda c: (not is_up(c), first_name(c)))
        rows = []
        for c in ordered:
            n, up = first_name(c), is_up(c)
            rows.append([cell(n, " · ".join(x for x in (short(c.get("ID")), "Liminal's service" if liminal_service(c) else "") if x)),
                         str(c.get("Image") or "–"), cell(str(c.get("State") or "–"), str(c.get("Status") or "") or None),
                         ports(c.get("Ports")) or "–", cell(created(c.get("CreatedAt")), str(c.get("RunningFor") or "") or None),
                         {"form": "logs", "title": "Logs", "values": {"name": n}, "label": f"Read the last lines of {n}'s log"},
                         {"form": "container", "title": "Stop…" if up else "Start…", "values": {"name": n, "action": "stop" if up else "start"},
                          "label": f"{'Stop' if up else 'Start'} {n}"},
                         {"form": "remove", "title": "Remove…", "values": {"name": n}, "label": f"Remove {n}"}])
        rows, note = self._capped(rows, on)
        table = {"title": "Containers", "note": note, "rows": rows,
                 "columns": [{"title": "Container"}, {"title": "Image"}, {"title": "State"}, {"title": "Ports"}, {"title": "Created"},
                             {"title": "Log"}, {"title": "Change"}, {"title": "Remove"}],
                 "empty": f"Not read: {problem}" if problem else f"No container on {shown.name}."}
        if containers:
            table["actions"] = [{"form": "container", "title": "Start, stop or restart…"}, {"form": "logs", "title": "Read a log…"},
                                {"form": "remove", "title": "Remove a container…"}]
        return table

    def _images_table(self, shown: Seen, images: list | None, containers: list, problem: str | None, on: str) -> dict:
        rows = []
        for i in sorted(images or [], key=image_order):
            ref = image_ref(i)
            tagged = ref != short(i.get("ID"))
            rows.append([cell(ref if tagged else "(untagged)", short(i.get("ID"))), str(i.get("Size") or "–"),
                         cell(str(i.get("CreatedSince") or "–"), created(i.get("CreatedAt"))),
                         ", ".join(users_of(i, containers)) or "–",
                         {"form": "rmi", "title": "Remove…", "values": {"image": ref}, "label": f"Remove the image {ref}"}])
        rows, note = self._capped(rows, on)
        return {"title": "Images", "note": note, "rows": rows,
                "columns": [{"title": "Image"}, {"title": "Size", "num": True}, {"title": "Created"}, {"title": "Used by"},
                            {"title": "Remove"}],
                "empty": f"Not read: {problem}" if problem else f"No image on {shown.name}.",
                "actions": [{"form": "pull", "title": "Pull an image…"}]}

    def _volumes_table(self, volumes: list | None, containers: list, problem: str | None, on: str) -> dict:
        rows = []
        for v in sorted(volumes or [], key=lambda v: (anonymous(str(v.get("Name") or "")), str(v.get("Name") or ""))):
            n = str(v.get("Name") or "")
            users = [first_name(c) for c in containers if n in names(c.get("Mounts"))]
            rows.append([cell(n[:12] + "…" if anonymous(n) else n, "anonymous" if anonymous(n) else str(v.get("Mountpoint") or "") or None),
                         str(v.get("Driver") or "–"), str(v.get("Scope") or "–"), ", ".join(users) or "–"])
        rows, note = self._capped(rows, on)
        return {"title": "Volumes", "note": note, "rows": rows,
                "columns": [{"title": "Volume"}, {"title": "Driver"}, {"title": "Scope"}, {"title": "Used by"}],
                "empty": f"Not read: {problem}" if problem else "No volume."}

    def _networks_table(self, networks: list | None, containers: list, problem: str | None, on: str) -> dict:
        rows = []
        for n in sorted(networks or [], key=lambda n: str(n.get("Name") or "")):
            name = str(n.get("Name") or "")
            flags = [word for word, key in (("internal", "Internal"), ("IPv6", "IPv6")) if str(n.get(key)).lower() == "true"]
            rows.append([cell(name, short(n.get("ID"))), str(n.get("Driver") or "–"), str(n.get("Scope") or "–"),
                         str(sum(1 for c in containers if name in names(c.get("Networks")))), ", ".join(flags) or "–"])
        rows, note = self._capped(rows, on)
        return {"title": "Networks", "note": note, "rows": rows,
                "columns": [{"title": "Network"}, {"title": "Driver"}, {"title": "Scope"}, {"title": "Containers", "num": True},
                            {"title": "Flags"}],
                "empty": f"Not read: {problem}" if problem else "No network."}

    @staticmethod
    def _forms(shown: Seen, listing: Listing) -> list[dict]:
        """The forms the platform's page draws (liminal-platform 0.6.0, status.forms): the fields are the hooks' arguments
        in order, the engine shown fixed in each; a change is asked once the user has confirmed it, a removal refused for
        a running container (an image a container was made from) asked again as a second, explicit confirmation."""
        engine = {"name": "engine", "label": "Engine", "type": "fixed", "value": shown.name}
        containers = sorted(listing.containers or [], key=lambda c: (not is_up(c), first_name(c)))
        forms = []
        if containers:
            pick = {"name": "name", "label": "Container", "type": "choice", "value": first_name(containers[0]),
                    "choices": [{"value": first_name(c), "title": first_name(c),
                                 "note": f"{c.get('State') or '?'}: {c.get('Status') or ''} · {c.get('Image') or ''}".strip()} for c in containers]}
            forms += [
                {"id": "container", "hook": "container", "title": "Start, stop or restart a container",
                 "note": f"On {shown.name}. Its files and its volumes stay whatever is done.",
                 "fields": [engine, pick, {"name": "action", "label": "Change", "type": "choice",
                                           "value": "stop" if is_up(containers[0]) else "start", "choices": [
                     {"value": "start", "title": "Start", "note": "runs it again as it was made"},
                     {"value": "stop", "title": "Stop", "note": f"it is given {STOP_S} s to end on its own, then killed"},
                     {"value": "restart", "title": "Restart", "note": "stopped as Stop does, then started again"}]}],
                 "submit": "Review",
                 "confirm": {"title": "{action} {name} on {engine}?",
                             "words": (f"The container {{name}} on {{engine}}: {{action}}. Stopping gives it {STOP_S} s to end on "
                                       "its own before it is killed; its files and its volumes stay."),
                             "yes": "Confirm"}},
                {"id": "remove", "hook": "remove_container", "title": "Remove a container",
                 "note": f"On {shown.name}. Its image and its volumes stay.",
                 "fields": [engine, pick, {"name": "force", "type": "accept", "title": "Remove it while it runs?", "yes": "Kill and remove",
                                           "words": "{name} is running: removed anyway, it is killed first (docker rm --force)."}],
                 "confirm": {"title": "Remove {name} from {engine}?",
                             "words": ("The container {name} is removed from {engine}: what it wrote outside its volumes goes with "
                                       "it; its image and its volumes stay."),
                             "yes": "Remove", "danger": True}},
                {"id": "logs", "hook": "logs", "title": "Read a container's log",
                 "note": f"Its last lines (at most {MAX_LOG_LINES:,}), its output and its errors as written; nothing is changed.",
                 "fields": [engine, pick, {"name": "lines", "label": "Lines", "type": "number", "value": LOG_LINES, "min": 1,
                                           "max": MAX_LOG_LINES}],
                 "submit": "Read", "confirm": False}]
        images = sorted(listing.images or [], key=image_order)
        if images:
            forms.append({"id": "rmi", "hook": "remove_image", "title": "Remove an image",
                          "note": f"On {shown.name}. Pulled again, it comes back.",
                          "fields": [engine, {"name": "image", "label": "Image", "type": "choice", "value": image_ref(images[0]),
                                              "choices": [{"value": image_ref(i), "title": image_ref(i),
                                                           "note": " · ".join(x for x in (str(i.get("Size") or ""),
                                                                                         ", ".join(users_of(i, containers))) if x)} for i in images]},
                                     {"name": "force", "type": "accept", "title": "Remove it although a container was made from it?",
                                      "yes": "Remove anyway",
                                      "words": ("{image} is what a container was made from: removed anyway (docker rmi --force), "
                                                "its tag goes; Docker still refuses while a running container uses it.")}],
                          "confirm": {"title": "Remove {image} from {engine}?",
                                      "words": ("The image {image} is removed from {engine} (docker rmi); another tag of the same image "
                                                "keeps it. Pulled again, it comes back."),
                                      "yes": "Remove", "danger": True}})
        forms.append(DockerPlugin._pull_form(shown.name))
        return forms

    @staticmethod
    def _pull_form(engine_name: str) -> dict:
        """The pull, on the engine named: a job (liminal-platform 0.19.0) whose lines the page follows as they come."""
        return {"id": "pull", "hook": "pull", "title": "Pull an image", "job": True,
                "note": "From its registry: Docker Hub unless its name says another (ghcr.io/..., quay.io/...).",
                "fields": [{"name": "engine", "label": "Engine", "type": "fixed", "value": engine_name},
                           {"name": "image", "label": "Image", "type": "text", "required": True,
                            "placeholder": "nginx:1.27, ghcr.io/owner/name:tag", "note": "its tag after a colon; latest when none"}],
                "submit": "Review",
                "confirm": {"title": "Pull {image} on {engine}?",
                            "words": ("{engine} downloads {image} from its registry (Docker Hub unless the name says another); "
                                      "its progress shows in the panel below as it comes, and a large image takes minutes. "
                                      "Nothing runs from it until a container is made. An image of the same name is replaced "
                                      "by the newer one; a container keeps the one it was made from. Docker Hub allows a "
                                      "limited number of anonymous pulls an hour from this network's address."),
                            "yes": "Pull"}}

    # -- finding an image (0.2.0) -----------------------------------------------------------------------------------------
    def _puller(self, r: Reading) -> Seen | None:
        """The engine an image is pulled on: the one shown, else the first that answers; None when none answers."""
        shown = r.engine(r.shown)
        return shown if shown is not None and shown.answering else next((e for e in r.engines if e.answering), None)

    def _found_table(self, found: Outcome | None, puller: Seen | None) -> dict:
        """The last search's results: what each image is and provides, where from, why it ranks where it does, a
        Details (what it is and holds) and a Pull (as a job, its progress in the panel) for each one that is one image."""
        search = {"form": "search", "field": "query", "value": found.query.text if found else "",
                  "placeholder": "what the image is for: nginx web server, postfix mail server with anti-spam, postgres …"}
        if found is None:
            return {"title": "Find an image", "search": search, "columns": [{"title": "Image"}], "rows": [],
                    "note": ("Searches Docker Hub (through a running Docker engine), Quay and Artifact Hub for anything, with "
                             "Liminal's picks for web servers, reverse proxies and mail servers; each result described, its "
                             "Details read on demand, and a Pull that shows its progress."),
                    "empty": "Type what the image is for above, then Search.",
                    "actions": [{"form": "details", "title": "Details of an image…"}]}
        rows = []
        for x in found.results[:FOUND_ROWS]:
            f = x.found
            what = (f.provides or f.description or "no description given").strip()
            if len(what) > DESCRIPTION_CHARS:
                what = what[:DESCRIPTION_CHARS - 1].rstrip() + "…"
            facts = " · ".join(v for v in (", ".join(f.categories[:3]), f.licence) if v)
            reasons = list(x.reasons)
            where = " · ".join(v for v in (registry_of(f.ref), shown_ref(f.ref) if shown_ref(f.ref) != f.name else "",
                                            f.publisher if f.publisher and f.publisher != f.name else "") if v)
            details = {"form": "detail", "title": "Details", "values": {"image": f.ref}, "label": f"Details of {f.name or shown_ref(f.ref)}"}
            if f.stack:
                pull = {"text": "a stack", "sub": "installed its own way"}
            elif puller is None:
                pull = {"text": "–", "sub": "no engine answers"}
            else:
                ref = pull_ref(f.ref, f.tag)
                pull = {"form": "pull", "title": "Pull…", "values": {"image": ref}, "label": f"Pull {ref} on {puller.name}",
                        "note": f"{ref} on {puller.name}"}
            rows.append([cell(f.name or shown_ref(f.ref), where or None), cell(what, facts or None),
                         cell(reasons[0] if reasons else "–", "; ".join(reasons[1:]) or None), details, pull])
        parts = [f"Read as: {found.query.said()}."]
        for name, a in found.sources():
            title = SOURCES.get(name, name) + (f" through {found.engine}" if name == "docker-hub" and found.engine else "")
            parts.append(f"{title}: " + (a["error"] if a.get("error") and not a.get("found") else
                                        f"{a.get('found', 0)} found" + (f" ({', '.join(a['terms'])})" if a.get("terms") else "")))
        if found.allowance:
            al = found.allowance
            parts.append(f"Docker Hub's anonymous pulls left from here: {al['left']} of {al['limit']} "
                         f"(per {al['hours']:g} hour{'s' if al['hours'] != 1 else ''})")
        parts += found.notes
        return {"title": f"Find an image: {len(found.results[:FOUND_ROWS])} for “{found.query.text}”", "search": search,
                "note": " · ".join(parts), "rows": rows,
                "columns": [{"title": "Image"}, {"title": "What it provides"}, {"title": "Why"}, {"title": "Details"},
                            {"title": "Pull"}],
                "empty": "Nothing found: other words, or another source (Everywhere asks them all).",
                "actions": [{"form": "details", "title": "Details of an image…"},
                            {"hook": "clear_search", "args": [], "title": "Clear", "note": "forgets these results"}]}

    def _search_forms(self, found: Outcome | None, puller: Seen | None) -> list[dict]:
        """The search (drawn as the box above its table), Details, and the pull of a result when no engine is shown
        (the engine forms' pull otherwise)."""
        forms = [
            {"id": "search", "hook": "search", "title": "Find an image", "confirm": False, "submit": "Search",
             "note": ("Docker Hub through a running Docker engine, Quay and Artifact Hub, with Liminal's picks for web servers, "
                      "reverse proxies and mail servers. Each registry asked receives these words."),
             "fields": [{"name": "query", "label": "What for", "type": "text", "required": True,
                         "value": found.query.text if found else "",
                         "placeholder": "nginx web server, postfix mail server with anti-spam, postgres, home assistant …"},
                        {"name": "where", "label": "Where", "type": "choice", "value": found.where if found else "all",
                         "choices": where_choices()}]},
            {"id": "details", "hook": "details", "title": "Details of an image", "confirm": False, "submit": "Show",
             "note": "What it provides, its description and README's first lines (its publisher's words), its newest tags.",
             "fields": [{"name": "image", "label": "Image", "type": "text", "required": True,
                         "placeholder": "nginx, mailserver/docker-mailserver, quay.io/owner/name"}]},
            # a result's own Details: its image given, nothing to fill or confirm, so the page asks it as it opens
            {"id": "detail", "hook": "details", "title": "Details", "confirm": False,
             "fields": [{"name": "image", "label": "Image", "type": "fixed"}]},
        ]
        return forms

    # -- what the page asks --------------------------------------------------------------------------------------
    def choose_engine(self, engine) -> dict:
        """The engine whose containers, images, volumes and networks the page shows (kept until the platform restarts)."""
        name = str(engine if engine is not None else "").strip()
        r = self._read()
        if r.engine(name) is None:
            raise ValueError(f"no Docker engine named {name!r} here: " + (", ".join(e.name for e in r.engines) or "none at all"))
        with self._rt.lock:
            self._rt.choice = name
        seen = self._read().engine(name)
        return {"said": f"showing {name}'s containers, images, volumes and networks", "ok": True,
                "lines": [seen.line() if seen else name, "kept until the platform restarts"]}

    def refresh(self) -> dict:
        """Every engine read again now (what was read is kept READ_S otherwise)."""
        r = self._read(fresh=True)
        answering = sum(1 for e in r.engines if e.answering)
        return {"said": f"read {plural(len(r.engines), 'engine')} now: {answering} answering", "ok": True,
                "lines": [e.line() for e in r.engines] or [NO_ENGINE]}

    def _ready(self, engine) -> tuple[Engine, Instance]:
        """The engine named, to be asked now: refused when it is not here, or is not to be asked (in a stopped WSL
        distribution: a change does not start it either)."""
        name = str(engine if engine is not None else "").strip()
        found = self._instances()
        i = next((x for x in found if x.name == name), None)
        if i is None:
            raise ValueError(f"no Docker engine named {name!r} here: " + (", ".join(x.name for x in found) or "none at all"))
        states = self._states() if wsl_target(i.command)[0] else {}
        why, _, _ = self._gate(i, states, self._plugins())
        if why:
            raise ValueError(f"{name} is not asked now: {why}")
        return self._engine(i), i

    @staticmethod
    def _name(name) -> str:
        n = str(name if name is not None else "").strip()
        if not CONTAINER.match(n):
            raise ValueError(f"not a container's name: {n!r}")
        return n

    @staticmethod
    def _image(image) -> str:
        ref = str(image if image is not None else "").strip()
        if not IMAGE.match(ref):
            raise ValueError(f"not an image's name: {ref!r} (as nginx:1.27, or ghcr.io/owner/name:tag)")
        return ref

    @staticmethod
    def _container_of(e: Engine, name: str) -> dict | None:
        for c in e.listing("containers"):
            if name in names(c.get("Names")) or (len(name) >= 12 and str(c.get("ID") or "").startswith(name)):
                return c
        return None

    def container(self, engine, name, action="start") -> dict:
        """A container started, stopped (given STOP_S to end on its own, then killed) or restarted: `action` start, stop or
        restart. Refused for one not there, one running already (start), one not running (stop)."""
        act = str(action if action is not None else "").strip().lower()
        if act not in ACTIONS:
            raise ValueError(f"a container is started, stopped or restarted, not {act!r}")
        n = self._name(name)
        e, i = self._ready(engine)
        c = self._container_of(e, n)
        if c is None:
            raise ValueError(f"no container named {n} on {i.name}")
        state = str(c.get("State") or "")
        if act == "start" and state == "running":
            raise ValueError(f"{n} is running already on {i.name}")
        if act == "stop" and state not in UP:
            raise ValueError(f"{n} is not running on {i.name} (it is {state or 'in no known state'})")
        try:
            if act == "start":
                e.start(n)
            elif act == "stop":
                e.stop(n, STOP_S)
            else:
                e.restart(n, STOP_S)
        finally:
            self._forget()
        after = self._container_of(e, n) or {}
        now = str(after.get("State") or "gone")
        ok = now == ACTIONS[act][2]
        lines = [f"now {now}" + (f": {after['Status']}" if after.get("Status") else "")]
        if not ok and act != "stop":
            lines.append("it did not stay up: its log says why (Logs)")
        return {"said": f"{n} {ACTIONS[act][1]} on {i.name}", "lines": lines, "ok": ok}

    def remove_container(self, engine, name, force=False) -> dict:
        """A container removed (its image and its volumes stay); a running one only once accepted (`force`: it is killed
        first)."""
        n = self._name(name)
        e, i = self._ready(engine)
        c = self._container_of(e, n)
        if c is None:
            raise ValueError(f"no container named {n} on {i.name}")
        up = is_up(c)
        if up and not yes(force):
            raise Refusal(f"{n} is running on {i.name}: stop it first, or remove it anyway (it is killed first)", accept="force")
        try:
            gone = e.remove(n, force=up)
        finally:
            self._forget()
        return {"said": f"{n} removed from {i.name}" if gone else f"{n} was gone from {i.name} already", "ok": True,
                "lines": [f"it was {c.get('State') or '?'} ({c.get('Status') or ''}), made from {c.get('Image') or '?'}".replace(" ()", "")]}

    def logs(self, engine, name, lines=None) -> dict:
        """A container's last `lines` lines (LOG_LINES unless given, at most MAX_LOG_LINES): its output and its errors in
        the order written, each at this machine's local time. Nothing is changed."""
        n = self._name(name)
        try:
            count = LOG_LINES if lines in (None, "") else int(lines)
        except (TypeError, ValueError):
            raise ValueError(f"lines is a whole number, not {lines!r}") from None
        if not 1 <= count <= MAX_LOG_LINES:
            raise ValueError(f"a log is read 1 to {MAX_LOG_LINES:,} lines at a time, not {count:,}")
        e, i = self._ready(engine)
        got = e.tail(n, count)
        when = span(e.last[1], e.last[2])
        if not got:
            return {"said": f"{n}'s log on {i.name} is empty", "lines": [], "ok": True}
        return {"said": f"the last {plural(len(got), 'line')} of {n}'s log on {i.name}" + (f" ({when})" if when else ""),
                "lines": got, "ok": True}

    def pull(self, engine, image, log=None) -> dict:
        """An image pulled from its registry (Docker Hub unless its name says another). As a job (`log`: the platform's
        panel, liminal-platform 0.19.0), each line docker prints is given to it as it comes. A compose stack the search
        lists is no image: refused, in words."""
        ref = self._image(image)
        stack = next((p for p in PICKS if p.stack and canonical(ref) == p.ref), None)
        if stack is not None:
            raise ValueError(f"{stack.name} is a compose stack of several images, not one to pull: {stack.stack}")
        e, i = self._ready(engine)
        if log is not None:
            log(f"pulling {ref} on {i.name} ({i.where})")
        try:
            out = e.pull_streaming(ref, log) if log is not None else e.pull(ref)
        finally:
            self._forget()
        said = [line.strip() for line in out.splitlines() if line.strip()]
        return {"said": f"{ref} pulled on {i.name}", "lines": said[-3:], "ok": True}

    # -- finding an image (0.2.0) -----------------------------------------------------------------------------------------
    def _searcher(self) -> Searcher:
        with self._rt.lock:
            if self._rt.searcher is None:
                self._rt.searcher = Searcher(self._http or Http(), wall=self._wall)
            return self._rt.searcher

    def _website(self) -> bool:
        """The user's setting: Docker Hub's website search too (read through the login the plugin is lent; off unless on)."""
        login = getattr(self, "login", None) or EnvironmentLogin()
        try:
            value = (login.variables((WEBSITE_VAR,)) or {}).get(WEBSITE_VAR) or ""
        except Exception:  # noqa: BLE001 - a login that cannot be asked: off
            return False
        return str(value).strip().lower() in ("on", "1", "true", "yes")

    def search(self, query, where="all") -> dict:
        """Images for `query` (anything: its words read, the known ones understood) from Docker Hub through the engine
        that answers, Quay, Artifact Hub and Liminal's picks (`where`: one of them, or all), ranked, kept for the page's
        table until the next search; nothing is pulled."""
        text = " ".join(str(query if query is not None else "").split())
        if not text:
            raise ValueError("say what the image is for: nginx web server, postfix mail server with anti-spam, postgres …")
        r = self._read()
        puller = self._puller(r)
        engine = None
        if puller is not None:
            try:  # asked now, as every change is: a distribution stopped since the last look is said, never started
                engine, _ = self._ready(puller.name)
            except ValueError:
                puller = None
        with self._rt.searching:
            found = self._searcher().search(text, str(where or "all"), engine, puller.name if puller else "", self._website())
        with self._rt.lock:
            self._rt.found = found
        n = len(found.results)
        lines = [f"read as: {found.query.said()}"]
        for name, a in found.sources():
            lines.append(f"{SOURCES.get(name, name)}: " + (a["error"] if a.get("error") and not a.get("found") else f"{a.get('found', 0)} found"))
        lines += [f"{k + 1}. {x.found.name or shown_ref(x.found.ref)}: {(x.found.provides or x.found.description or '')[:160]}"
                  for k, x in enumerate(found.results[:5])]
        return {"said": f"{n} image{'' if n == 1 else 's'} for “{text}”: the table below lists them" if n else f"nothing found for “{text}”",
                "lines": lines, "ok": True}

    def details(self, image) -> dict:
        """What one image is and holds, in words: where from and by whom, why it ranks where it does, what it provides,
        its description and README's first lines (its publisher's words, shown as plain text), its newest tags. Reads
        only; nothing is pulled."""
        ref = str(image if image is not None else "").strip()
        if not ref or len(ref) > 255 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*", ref):
            raise ValueError(f"not an image's name: {ref!r} (as nginx, mailserver/docker-mailserver, quay.io/owner/name)")
        with self._rt.lock:
            found = self._rt.found
        title, lines = self._searcher().details(ref, found)
        return {"said": title, "lines": lines, "ok": True}

    def clear_search(self) -> dict:
        with self._rt.lock:
            had = self._rt.found
            self._rt.found = None
        return {"said": "the search's results forgotten" if had else "no results to forget", "ok": True}

    def remove_image(self, engine, image, force=False) -> dict:
        """An image removed (docker rmi); one a container was made from only once accepted (`force`: docker rmi --force;
        Docker still refuses while a running container uses it)."""
        ref = self._image(image)
        e, i = self._ready(engine)
        wanted = ref if (":" in ref.rsplit("/", 1)[-1] or "@" in ref or re.fullmatch(r"[0-9a-f]{12,64}", ref)) else f"{ref}:latest"
        img = next((x for x in e.listing("images") if image_ref(x) in (ref, wanted) or short(x.get("ID")) == short(ref)), None)
        if img is None:
            raise ValueError(f"no image {ref} on {i.name}")
        users = users_of(img, e.listing("containers"))
        if users and not yes(force):
            raise Refusal(f"{ref} is what {', '.join(users)} {'was' if len(users) == 1 else 'were'} made from on {i.name}: remove "
                          f"{'it' if len(users) == 1 else 'them'} first, or remove the image anyway", accept="force")
        try:
            out = e.remove_image(ref, force=bool(users))
        finally:
            self._forget()
        return {"said": f"{ref} removed from {i.name}", "ok": True,
                "lines": [line.strip() for line in out.splitlines() if line.strip()][:6]}


MACHINE = DockerPlugin()
