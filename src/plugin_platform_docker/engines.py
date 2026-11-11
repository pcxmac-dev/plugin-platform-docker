"""The Docker plugin's commands and what they answer, beside the library's docker.py: the windowless runner every
docker command goes through (CREATE_NO_WINDOW on Windows, its output read as UTF-8 whatever this machine's code page
is), `Engine` (the library's Docker with the listings and the changes the page needs besides its own), whether an
engine is reached through WSL and in which distribution, and the engines' answers in words."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
from datetime import datetime, timezone

from liminal_libs.docker import Docker, DockerError, Instance
from liminal_libs.proc import no_window

READ_TIMEOUT_S = 60.0  # a listing's command at most
PULL_S = 1800.0  # a pull at most (a large image over a slow line), its lines shown as they come
STOP_S = 20  # seconds a container is given to end on its own before it is killed
LINE_CHARS = 2000  # a log line longer than this is cut
UTF8_WSL = {"WSL_UTF8": "1"}  # wsl's own words in UTF-8 (UTF-16 otherwise)
LISTINGS = {  # what each listing asks (docker ... --format "{{json .}}": one JSON object a line)
    "containers": ("ps", "-a", "--no-trunc"),
    "images": ("images", "--no-trunc"),
    "volumes": ("volume", "ls"),
    "networks": ("network", "ls", "--no-trunc"),
}
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z ?(.*)$")  # docker logs --timestamps


def text(raw) -> str:
    """A command's output as text: UTF-8 (a container's log may hold any bytes: replaced, never raised), or UTF-16 for
    wsl's own words when it does not honor WSL_UTF8 (a NUL after every letter)."""
    if isinstance(raw, str):
        return raw
    raw = raw or b""
    if len(raw) >= 2 and raw[1:2] == b"\x00" and raw.count(b"\x00") * 3 >= len(raw):
        return raw.decode("utf-16-le", "replace").replace("﻿", "")
    return raw.decode("utf-8", "replace")


def run(args, timeout: float) -> tuple[int, str, str]:
    """`args` run without a window of its own (the platform has no console: a console child would open a Windows
    Terminal window that stays) and without this process's standard input: (exit code, output, errors). A command that
    cannot run or runs too long is a DockerError, as the library's own runner says it."""
    args = [str(a) for a in args]
    try:
        done = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                              env={**os.environ, **UTF8_WSL}, **no_window())
    except subprocess.TimeoutExpired:
        raise DockerError(f"{said(args)} took more than {timeout:g} s") from None
    except OSError as e:
        raise DockerError(f"{program(args[0]) if args else 'the command'} could not run: {e}") from None
    return done.returncode, text(done.stdout), text(done.stderr)


def stream(args, timeout: float, line) -> tuple[int, str]:
    """`args` run as `run` runs them (windowless, no standard input), each line it prints given to `line` as it comes (a
    pull's progress, followed on the platform's page): (exit code, what it wrote to its errors). Running past `timeout`,
    it is killed: a DockerError."""
    args = [str(a) for a in args]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                env={**os.environ, **UTF8_WSL}, **no_window())
    except OSError as e:
        raise DockerError(f"{program(args[0]) if args else 'the command'} could not run: {e}") from None
    errors: list[bytes] = []
    reader = threading.Thread(target=lambda: errors.append(proc.stderr.read()), name="docker-stream-errors", daemon=True)
    reader.start()
    killed = threading.Event()

    def kill() -> None:
        killed.set()
        proc.kill()

    timer = threading.Timer(timeout, kill)
    timer.daemon = True
    timer.start()
    try:
        for raw in iter(proc.stdout.readline, b""):
            got = text(raw).rstrip("\r\n")
            if got.strip():
                line(got[:LINE_CHARS])
        proc.wait()
    finally:
        timer.cancel()
        reader.join(5)
    if killed.is_set():
        raise DockerError(f"{said(args)} took more than {timeout:g} s: stopped")
    return proc.returncode, text(b"".join(errors))


def program(path) -> str:
    """A program by its name: C:/Windows/System32/wsl.exe as wsl."""
    name = os.path.basename(str(path))
    return name[:-4] if name.lower().endswith(".exe") else name


def said(args) -> str:
    """A command line in words, its program by name (wsl -d Liminal-Ubuntu --exec docker ps)."""
    args = [str(a) for a in args]
    return " ".join([program(args[0]), *args[1:6]]) if args else ""


class Engine(Docker):
    """The library's Docker, through the plugin's runner (`runner(args, timeout) -> (code, out, err)`: `run` unless a
    test's stand-in is given), with what the page reads and changes besides the library's own: the listings (every
    field docker ps, images, volume ls and network ls give: when a container was made, its mounts and networks), a
    container restarted, an image removed, a container's last log lines with what it wrote to its errors (docker logs
    gives those on its own standard error)."""

    def __init__(self, *args, runner=None, streamer=None, **kw):
        self.last: tuple[int, str, str] = (0, "", "")  # the last command's exit code, output and errors
        given = runner if runner is not None else run
        self._stream = streamer if streamer is not None else stream  # (args, timeout, line) -> (code, errors)

        def recorded(argv, timeout):
            self.last = given(argv, timeout)
            return self.last
        super().__init__(*args, runner=recorded, **kw)

    def line(self, *args: str) -> list[str]:
        """The command line the library's `_run` gives `args` (its prefix through WSL, its context or its host)."""
        return [self.command, *self.argv[1:], *(("--context", self.context) if self.context else ()),
                *(("-H", self.host) if self.host else ()), *args]

    def pull_streaming(self, ref: str, log, timeout: float = PULL_S) -> str:
        """`docker pull ref`, each line it prints given to `log` as it comes (a job's panel); what it printed. Refused,
        or failed: a DockerError in docker's own words."""
        self.log(f"docker: pulling {ref} on {self.where}")
        printed: list[str] = []

        def each(s: str) -> None:
            printed.append(s)
            log(s)
        code, errors = self._stream(self.line("pull", ref), timeout, each)
        if code != 0:
            raise DockerError((errors or "\n".join(printed[-3:]) or f"docker pull {ref} failed ({code})").strip())
        return "\n".join(printed)

    def rows(self, *args: str, timeout: float = READ_TIMEOUT_S) -> list[dict]:
        """A listing's rows: docker's JSON objects, one a line (a line that is not one is left out)."""
        raw = self._run(*args, "--format", "{{json .}}", timeout=timeout)
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out

    def listing(self, kind: str) -> list[dict]:
        """The containers (all, stopped too), the images, the volumes or the networks."""
        return self.rows(*LISTINGS[kind])

    def restart(self, name: str, seconds: int = STOP_S) -> None:
        self.log(f"docker: restarting {name}")
        self._run("restart", "-t", str(seconds), name)

    def remove_image(self, ref: str, force: bool = False) -> str:
        self.log(f"docker: removing the image {ref}")
        return self._run("rmi", *(("-f",) if force else ()), ref)

    def tail(self, name: str, lines: int) -> list[str]:
        """A container's last `lines` lines, what it wrote to its output and to its errors in the order written (each
        stamped by docker: --timestamps), each at this machine's local time. DockerError when docker refuses."""
        out = self._run("logs", "--tail", str(int(lines)), "--timestamps", name, check=False, timeout=READ_TIMEOUT_S)
        code, _, err = self.last
        if code != 0:
            raise DockerError((err or out or f"docker logs {name} failed ({code})").strip())
        return log_lines(out, err)[-int(lines):]


def wsl_target(command: str) -> tuple[bool, str]:
    """Whether an engine's command reaches it through WSL (`wsl -d Liminal-Ubuntu --exec docker`), and the distribution
    it names ("" for WSL's default one)."""
    try:
        argv = shlex.split(str(command or ""))
    except ValueError:
        return False, ""
    if not argv:
        return False, ""
    if argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in ("wsl", "wsl.exe"):
        return False, ""
    for i, a in enumerate(argv[1:], 1):
        if a in ("--exec", "-e", "--"):
            break
        if a in ("-d", "--distribution") and i + 1 < len(argv):
            return True, argv[i + 1]
    return True, ""


def broken(i: Instance) -> bool:
    """An entry docker.instances made for a machine plugin whose instances() failed (its `where` holds the error)."""
    return bool(i.source) and i.source == i.name and str(i.where).startswith(f"{i.name}: ")


def words(e: Exception) -> str:
    """An engine's refusal or failure in words: docker's own last line, said plainly where it is a known one."""
    s = str(e).strip()
    last = s.splitlines()[-1].strip() if s else type(e).__name__
    low = s.lower()
    if "execvpe(docker)" in low or "docker: not found" in low or "docker: command not found" in low:
        return "Docker is not installed there"
    if "cannot connect to the docker daemon" in low or "is the docker daemon running" in low:
        return "its engine is not running (the docker command answers, its daemon does not)"
    if "dockerdesktoplinuxengine" in low or ("docker_engine" in low and "cannot find the file" in low):
        return "Docker Desktop is not running"
    if "permission denied" in low and "docker.sock" in low:
        return "permission denied: the user is not in the docker group"
    return last


def short(identifier) -> str:
    """An image's, a container's or a network's id as docker shows it: 12 hexadecimal digits."""
    s = str(identifier or "")
    return (s.split(":", 1)[1] if s.startswith("sha256:") else s)[:12]


def anonymous(name: str) -> bool:
    """A volume docker named itself (64 hexadecimal digits): one a container made without a name."""
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(name or "")))


def local_time(moment: datetime, fmt: str = "%b %d %H:%M") -> str:
    """An aware time at this machine's local time (in UTC where Windows cannot take it there: a time near 1970)."""
    try:
        return moment.astimezone().strftime(fmt)
    except (OSError, OverflowError, ValueError):
        return moment.astimezone(timezone.utc).strftime(fmt) + " UTC"


def created(value) -> str:
    """docker's "2026-11-08 09:14:02 +0000 UTC" at this machine's local time; as it is when it is not one."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.\d+)? ([+-]\d{4})", str(value or ""))
    if not m:
        return str(value or "") or "–"
    return local_time(datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%Y-%m-%d %H:%M:%S %z"))


def ports(value) -> str:
    """A container's published ports as docker lists them, the IPv6 twin of an IPv4 binding on every address left out
    (0.0.0.0:8080->80/tcp, [::]:8080->80/tcp: the first)."""
    parts = [p.strip() for p in str(value or "").split(",") if p.strip()]
    v4 = {p.split(":", 1)[1] for p in parts if p.startswith("0.0.0.0:")}
    return ", ".join(p for p in parts if not (p.startswith("[::]:") and p[5:] in v4))


def names(value) -> list[str]:
    """A comma separated field (a container's Names, Mounts, Networks) as a list (podman gives lists already)."""
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    return [p.strip() for p in str(value or "").split(",") if p.strip()]


def liminal_service(row: dict) -> bool:
    """A container the framework runs as one of its services (docker.Service labels it liminal=service)."""
    labels = row.get("Labels")
    if isinstance(labels, dict):
        return labels.get("liminal") == "service"
    return bool(re.search(r"(^|,)liminal=service(,|$)", str(labels or "")))


def image_ref(row: dict) -> str:
    """An image's reference: repository:tag, else its id (an image without a tag)."""
    repo, tag = str(row.get("Repository") or ""), str(row.get("Tag") or "")
    if repo and repo != "<none>":
        return f"{repo}:{tag}" if tag and tag != "<none>" else repo
    return short(row.get("ID"))


def users_of(image: dict, containers: list[dict]) -> list[str]:
    """The containers made from an image (their Image is its reference, its repository when tagged latest, or its id)."""
    ref, repo, tag = image_ref(image), str(image.get("Repository") or ""), str(image.get("Tag") or "")
    refs = {ref, *([repo] if tag == "latest" else [])}
    ident = short(image.get("ID"))
    return [n for c in containers for n in names(c.get("Names"))[:1]
            if str(c.get("Image") or "") in refs or (ident and short(c.get("Image")) == ident)]


def log_lines(out: str, err: str) -> list[str]:
    """docker logs --timestamps' two streams as one, in the order written, each line at this machine's local time and
    cut at LINE_CHARS; a line without a stamp kept where its stream had it."""
    rows = []
    for n, stream in enumerate((out or "", err or "")):
        for i, line in enumerate(stream.splitlines()):
            m = STAMP.match(line)
            if m:
                rows.append((f"{m.group(1)}.{(m.group(2) or '').ljust(9, '0')}", n, i, m.group(1), m.group(3)))
            elif line.strip():
                rows.append(("", n, i, "", line))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    shown = []
    for _, _, _, stamp, body in rows:
        when = ""
        if stamp:
            when = local_time(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc), "%H:%M:%S") + " "
        shown.append((when + body)[:LINE_CHARS])
    return shown


def span(out: str, err: str) -> str:
    """The first and the last stamp of a log, at this machine's local time ("" when it has none)."""
    stamps = sorted(m.group(1) for line in (out or "").splitlines() + (err or "").splitlines() for m in [STAMP.match(line)] if m)
    if not stamps:
        return ""
    first, last = (datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) for s in (stamps[0], stamps[-1]))
    return local_time(first) if stamps[0][:16] == stamps[-1][:16] else f"{local_time(first)} to {local_time(last)}"
