"""The registries the image search asks, and how (0.2.0). Only documented ways unless the user turns another on (the user,
2026-11-10, of Docker Hub: "Engine only"): Docker Hub through the Docker engine's own search (`docker search`, the Engine
API's /images/search: it needs an engine that answers), Docker Hub's documented repository and tags API for what an
image is and holds, Quay.io's API, Artifact Hub's API, any registry's tags through the OCI distribution API (an anonymous
token where it asks for one), Docker Hub's pull allowance as its documented check reads it (a HEAD, which spends no
pull). Docker Hub's website search (undocumented: Docker's terms allow automated access only through documented APIs)
only when its setting is on.

Every request: https only, a turn per host (spaced so no registry is pressed: Docker Hub allows 180 a minute, Quay "a
few a second", Artifact Hub publishes none), what was read kept a while (a search 10 min, a detail 5), a host that asks
to wait (429, Artifact Hub's 403) left alone until it said, an answer cut at MAX_BYTES, the plugin's own name as its user
agent (nothing of the user's), and no header ever logged or kept (Docker Hub's echo the asker's address). A registry
that cannot be asked, or answers with something unexpected, is a SourceError: said beside the results, the search goes
on without it. Descriptions and READMEs are their publishers' words: kept as plain text, never followed.
"""
from __future__ import annotations

import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

VERSION = "0.2.0"  # the plugin's (a test keeps it equal to __version__)
USER_AGENT = f"plugin-platform-docker/{VERSION}"
HUB = "https://hub.docker.com"
QUAY = "https://quay.io"
ARTIFACTHUB = "https://artifacthub.io"
DOCKER_AUTH = "https://auth.docker.io"
DOCKER_REGISTRY = "https://registry-1.docker.io"
SPACING = {"hub.docker.com": 0.4, "quay.io": 0.5, "artifacthub.io": 1.0, "auth.docker.io": 0.3, "registry-1.docker.io": 0.3}
DEFAULT_SPACING = 0.5  # any other registry
TIMEOUT_S = 8.0  # each wait for the next bytes
ANSWER_S = 20.0  # a whole answer at most (a registry feeding it slowly is cut)
ENGINE_SEARCH_S = 20.0  # `docker search` through the engine (in WSL: a few seconds)
MAX_BYTES = 4 << 20
PLAIN_CHARS = 32_000  # a publisher's text read for its first lines at most (24 lines are shown)
SEARCH_TTL_S = 600.0
DETAIL_TTL_S = 300.0
CACHE_MAX = 160
BUSY_S = 60.0  # a host that asked to wait without saying how long
BUSY_MAX_S = 900.0
README_LINES = 24  # a README's first lines shown in Details
LINE_CHARS = 300
SOURCES = {  # a source's name -> its title
    "docker-hub": "Docker Hub", "hub-website": "Docker Hub (website search)", "quay": "Quay.io",
    "artifact-hub": "Artifact Hub", "catalog": "Liminal's picks",
}


class SourceError(Exception):
    """A registry that could not be asked, or answered with something unexpected."""


class Busy(SourceError):
    """A registry that asked to wait: left alone until it said."""


@dataclass
class Found:
    """An image as the sources describe it, merged across them by its canonical reference (`ref`: no tag)."""

    ref: str
    name: str = ""
    description: str = ""
    publisher: str = ""
    official: bool = False  # a Docker Official Image, or an official package on Artifact Hub
    verified: bool = False  # a verified publisher (Docker Hub's, Artifact Hub's)
    open_source: bool = False  # Docker-Sponsored Open Source
    signed: bool = False  # a cosign signature attached (Artifact Hub; not verified here)
    stars: int | None = None
    pulls: int | None = None
    popularity: float | None = None  # Quay: repository actions in the last 7 days
    updated: float | None = None  # unix seconds
    tag: str = ""  # a tag known to be there (or the one suggested)
    tag_count: int | None = None  # None: not read
    categories: tuple = ()
    keywords: tuple = ()
    archived: bool = False
    deprecated: bool = False
    needs_login: str = ""  # why it cannot be pulled without signing in to its registry
    stack: str = ""  # a compose stack's install page: listed, never pulled as one
    provides: str = ""  # what it provides (a pick's words)
    licence: str = ""
    note: str = ""
    scan: str = ""  # a vulnerability summary (Artifact Hub's)
    page: str = ""
    sources: tuple = ()
    terms: tuple = ()  # the search terms that found it
    pick: object = None  # the catalog's Pick when it is one
    extra: dict = field(default_factory=dict)  # a source's own handles (Artifact Hub's repository and package names)


# -- references ---------------------------------------------------------------------------------------------------------
def canonical(ref: str) -> str:
    """An image's reference without its tag or digest, as one name: lower case; Docker Hub's as docker.io (index.docker.io,
    registry-1.docker.io and none at all), library/ before its single names; lscr.io as ghcr.io (it fronts it)."""
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", str(ref or "").strip().lower()).split("@", 1)[0].strip("/")
    head, _, last = s.rpartition("/")
    last = last.split(":", 1)[0]
    parts = [p for p in ((head + "/" + last) if head else last).split("/") if p]
    if not parts:
        return ""
    if len(parts) == 1 or not ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        parts = ["docker.io", *parts]
    if parts[0] in ("index.docker.io", "registry-1.docker.io", "registry.hub.docker.com"):
        parts[0] = "docker.io"
    if parts[0] == "lscr.io":
        parts[0] = "ghcr.io"
    if parts[0] == "docker.io" and len(parts) == 2:
        parts.insert(1, "library")
    return "/".join(parts)


def shown(ref: str) -> str:
    """A reference as people write it: nginx, mailserver/docker-mailserver, quay.io/x/y."""
    if ref.startswith("docker.io/library/"):
        return ref[len("docker.io/library/"):]
    return ref[len("docker.io/"):] if ref.startswith("docker.io/") else ref


def registry_of(ref: str) -> str:
    host = ref.split("/", 1)[0]
    return {"docker.io": "Docker Hub", "quay.io": "Quay.io", "ghcr.io": "GitHub (ghcr.io)", "public.ecr.aws": "Amazon ECR Public",
            "mcr.microsoft.com": "Microsoft (MCR)", "registry.gitlab.com": "GitLab", "github.com": "GitHub (a compose project)"}.get(host, host)


def hub_parts(ref: str) -> tuple[str, str]:
    """A Docker Hub reference's namespace and repository (library for an official image)."""
    path = ref[len("docker.io/"):] if ref.startswith("docker.io/") else ref
    ns, _, repo = path.partition("/")
    return (ns, repo) if repo else ("library", ns)


def hub_page(ref: str) -> str:
    ns, repo = hub_parts(ref)
    return f"{HUB}/_/{repo}" if ns == "library" else f"{HUB}/r/{ns}/{repo}"


def pull_ref(ref: str, tag: str) -> str:
    """What `docker pull` is given: the reference with its tag (latest when none)."""
    return f"{shown(ref)}:{tag or 'latest'}" if ref.startswith("docker.io/") else f"{ref}:{tag or 'latest'}"


def plain(markdown: str, lines: int = README_LINES) -> list[str]:
    """A publisher's Markdown or HTML as plain lines (its words only: no markup, no images, links as their text), the
    first `lines`, each cut at LINE_CHARS. Never followed: shown, as words."""
    # its start alone (the lines shown come from there), and every pattern bounded: a text of unclosed brackets or comments
    # cannot make the reading slow
    text = str(markdown or "")[:PLAIN_CHARS]
    text = re.sub(r"<!--.{0,4000}?-->", " ", text, flags=re.S)
    text = re.sub(r"```.{0,8000}?```", " ", text, flags=re.S)
    text = re.sub(r"<[^>]{0,500}>", " ", text)  # HTML tags
    text = re.sub(r"(?m)^ {0,3}\[[^\]\n]{1,200}\]:[ \t]*\S+.*$", "", text)  # a reference's definition: "[ci::status]: https://..."
    text = re.sub(r"!\[[^\]\n]{0,300}\](\([^)\n]{0,500}\)|\[[^\]\n]{0,200}\])?", "", text)  # images: inline, by reference, alone
    text = re.sub(r"\[\s{0,10}\](\([^)\n]{0,500}\)|\[[^\]\n]{0,200}\])", "", text)  # a link left with no words (it held an image)
    text = re.sub(r"\[([^\]\n]{0,300})\](\([^)\n]{0,500}\)|\[[^\]\n]{0,200}\])", r"\1", text)  # links: their words
    out = []
    for raw in text.splitlines():
        line = re.sub(r"^[#>*\-+\s|]+", "", raw).replace("**", "").replace("__", "").replace("`", "").strip(" |")
        line = " ".join(line.split())
        if not line or set(line) <= set("-=:|"):
            continue
        out.append(line[:LINE_CHARS])
        if len(out) >= lines:
            break
    return out


def first_line(text: str) -> str:
    got = plain(text, 1)
    return got[0] if got else ""


def epoch(value) -> float | None:
    """An ISO time ("2026-11-10T04:52:25.48Z") or unix seconds as unix seconds."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.isdigit():
        return float(s)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    try:  # Quay's "Mon, 09 Nov 2026 04:28:24 -0000"
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z").timestamp()
    except ValueError:
        return None


def number(value) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# -- the requests -------------------------------------------------------------------------------------------------------
class _SameHostHttps(urllib.request.HTTPRedirectHandler):
    """Redirects followed only to https on the same host (a bearer token never goes elsewhere, nothing in the clear);
    any other is the registry's 3xx, said as such."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new.scheme != "https" or new.hostname != old.hostname:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostHttps)


def _read_all(r, deadline: float) -> bytes:
    """An answer's body, read until MAX_BYTES + 1 or `deadline` (a registry feeding it a byte at a time is cut)."""
    chunks, size = [], 0
    while size <= MAX_BYTES:
        if time.monotonic() > deadline:
            raise SourceError(f"its answer took more than {ANSWER_S:g} s")
        chunk = r.read(min(1 << 16, MAX_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def _urlopen(method: str, url: str, headers: dict, timeout: float) -> tuple[int, dict, bytes]:
    """One request: (status, headers in lower case, body cut at MAX_BYTES + 1). An HTTP error is its status, not raised;
    no answer at all, or one too slow, is a SourceError."""
    request = urllib.request.Request(url, headers=headers, method=method)
    deadline = time.monotonic() + ANSWER_S
    try:
        with _OPENER.open(request, timeout=timeout) as r:  # noqa: S310 - the registries' https addresses only
            return r.status, {k.lower(): v for k, v in r.headers.items()}, _read_all(r, deadline)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(1 << 16)
        except (OSError, http.client.HTTPException):
            body = b""
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, http.client.HTTPException) as e:
        raise SourceError(f"no answer ({getattr(e, 'reason', e) or type(e).__name__})") from None


class Http:
    """The registries' requests: a turn per host, the cache, a host's request to wait, the size cap; `opener(method, url,
    headers, timeout) -> (status, headers, body)` (a test's stand-in, else urllib), `sleep` and `clock` alike."""

    def __init__(self, opener=None, clock=None, sleep=None):
        self._open = opener or _urlopen
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}
        self._busy: dict[str, float] = {}
        self._cache: dict[str, tuple[float, object]] = {}
        self.asked = 0  # requests made (not cached): for the tests and the facts

    def forget(self) -> None:
        with self._lock:
            self._cache.clear()

    def busy(self, host: str) -> float:
        """Seconds a host asked to be left alone still (0: none)."""
        with self._lock:
            return max(0.0, self._busy.get(host, 0.0) - self._clock())

    def _turn(self, host: str) -> None:
        with self._lock:
            now = self._clock()
            until = self._busy.get(host, 0.0)
            if until > now:
                raise Busy(f"{host} asked to wait ({int(until - now) + 1} s more)")
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + SPACING.get(host, DEFAULT_SPACING)
        if at > now:
            self._sleep(at - now)

    def request(self, method: str, url: str, headers: dict | None = None) -> tuple[int, dict, bytes]:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise SourceError(f"not an https address: {url[:80]}")
        host = parts.hostname
        self._turn(host)
        sent = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        status, got, body = self._open(method, url, sent, TIMEOUT_S)
        self.asked += 1
        if status == 429 or (host == "artifacthub.io" and status == 403):
            wait = number(got.get("retry-after")) or BUSY_S
            with self._lock:
                self._busy[host] = self._clock() + min(float(wait), BUSY_MAX_S)
            raise Busy(f"{host} asked to wait ({min(int(wait), int(BUSY_MAX_S))} s)")
        if len(body) > MAX_BYTES:
            raise SourceError(f"{host} answered more than {MAX_BYTES >> 20} MB")
        return status, got, body

    def get_json(self, url: str, ttl: float = SEARCH_TTL_S, headers: dict | None = None):
        """A GET answered in JSON, kept `ttl` seconds; anything but 200, or no JSON, a SourceError."""
        now = self._clock()
        with self._lock:
            kept = self._cache.get(url)
            if kept is not None and kept[0] > now:
                return kept[1]
        status, _, body = self.request("GET", url, headers)
        host = urllib.parse.urlsplit(url).hostname
        if status == 404:
            raise SourceError(f"{host}: not found")
        if status != 200:
            raise SourceError(f"{host} answered {status}")
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            raise SourceError(f"{host} answered something that is not JSON") from None
        with self._lock:
            self._cache[url] = (self._clock() + ttl, data)
            if len(self._cache) > CACHE_MAX:  # the soonest to go, gone
                for k, _ in sorted(self._cache.items(), key=lambda kv: kv[1][0])[: len(self._cache) - CACHE_MAX]:
                    del self._cache[k]
        return data


def _q(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _dict(data, what: str) -> dict:
    if not isinstance(data, dict):
        raise SourceError(f"{what} answered in an unexpected shape")
    return data


# -- Docker Hub, through the engine (documented: the Engine API's image search) -----------------------------------------
def hub_by_engine(engine, term: str, limit: int = 40) -> list[Found]:
    """Docker Hub searched by the engine (`docker search`): names and descriptions, several words ORed; no pull counts
    (Docker Hub's repository API adds them)."""
    term = str(term or "").strip().lstrip("-")  # never read by docker as a flag
    if not term:
        return []
    rows = engine.rows("search", "--no-trunc", "--limit", str(int(limit)), term, timeout=ENGINE_SEARCH_S)
    out = []
    for r in rows:
        name = str(r.get("Name") or "").strip()
        ref = canonical(name)
        if not ref.startswith("docker.io/"):
            continue
        official = str(r.get("IsOfficial") or "").strip().lower() in ("[ok]", "ok", "true", "1")
        out.append(Found(ref=ref, name=shown(ref), description=str(r.get("Description") or "").strip(),
                         stars=number(r.get("StarCount")), official=official, page=hub_page(ref),
                         publisher="Docker Official Images" if official else hub_parts(ref)[0], sources=("docker-hub",),
                         terms=(term,)))
    return out


# -- Docker Hub's documented repository and tags API --------------------------------------------------------------------
def hub_repository(http: Http, ref: str) -> dict:
    """What Docker Hub says of a repository (anonymous; documented): its descriptions, counts, dates, categories."""
    ns, repo = hub_parts(ref)
    return _dict(http.get_json(f"{HUB}/v2/namespaces/{_q(ns)}/repositories/{_q(repo)}", DETAIL_TTL_S), "Docker Hub")


def hub_tags(http: Http, ref: str, n: int = 10) -> tuple[int | None, list[dict]]:
    """A Docker Hub repository's newest tags (anonymous; documented): (how many it has, [{name, updated, size, platforms,
    active}])."""
    ns, repo = hub_parts(ref)
    data = _dict(http.get_json(f"{HUB}/v2/namespaces/{_q(ns)}/repositories/{_q(repo)}/tags?page_size={int(n)}", DETAIL_TTL_S),
                 "Docker Hub's tags")
    tags = []
    for t in data.get("results") or []:
        if not isinstance(t, dict) or not t.get("name"):
            continue
        plats = sorted({f"{i.get('os')}/{i.get('architecture')}" + (f"/{i['variant']}" if i.get("variant") else "")
                        for i in t.get("images") or [] if isinstance(i, dict) and i.get("os") not in (None, "", "unknown")})
        tags.append({"name": str(t["name"]), "updated": epoch(t.get("last_updated") or t.get("tag_last_pushed")),
                     "size": number(t.get("full_size")), "platforms": plats, "active": t.get("tag_status") != "inactive",
                     "digest": str(t.get("digest") or "")})
    return number(data.get("count")), tags


def hub_has_tag(http: Http, ref: str, tag: str) -> bool:
    """Whether a Docker Hub repository holds `tag` (anonymous; documented: a tag read by its name, 404 when absent)."""
    ns, repo = hub_parts(ref)
    try:
        _dict(http.get_json(f"{HUB}/v2/namespaces/{_q(ns)}/repositories/{_q(repo)}/tags/{_q(tag)}", DETAIL_TTL_S), "Docker Hub's tag")
    except SourceError as e:
        if "not found" in str(e):
            return False
        raise
    return True


ARTIFACT_TAG = re.compile(r"^sha256-[0-9a-f]+(\.(sig|att|sbom))?$|\.(sig|att|sbom)$")  # a signature, an attestation: no image
UNSTABLE_TAG = re.compile(r"(^|[^a-z])(dev|nightly|beta|alpha|rc\d*|edge|canary|test|testing|snapshot|unstable|preview)([^a-z]|$)"
                          r"|\d[ab]\d+$", re.I)  # also "2026.11.0b3", "1.0a1"


def tag_to_offer(names: list[str]) -> str:
    """Of a page of tags (newest first), the one to offer when 'latest' is not there: the newest that is an image (no
    signature or attestation) and not a development build; else the newest image; "" for none."""
    images = [n for n in names if not ARTIFACT_TAG.search(n)]
    return next((n for n in images if not UNSTABLE_TAG.search(n)), images[0] if images else "")


def enrich_from_hub(f: Found, repo: dict) -> None:
    """A Docker Hub result given what its repository API says: pulls, stars, when updated, categories, descriptions."""
    f.pulls = number(repo.get("pull_count")) if repo.get("pull_count") is not None else f.pulls
    f.stars = number(repo.get("star_count")) if repo.get("star_count") is not None else f.stars
    f.updated = epoch(repo.get("last_updated")) or f.updated
    cats = tuple(str(c.get("name") or "") for c in repo.get("categories") or [] if isinstance(c, dict) and c.get("name"))
    f.categories = tuple(dict.fromkeys(f.categories + cats))
    if not f.description:
        f.description = str(repo.get("description") or "").strip()
    if str(repo.get("status_description") or "").lower() == "inactive":
        f.note = f.note or "Docker Hub marks it inactive (nothing pushed or pulled for a long while)"
    f.extra["full_description"] = str(repo.get("full_description") or "")


# -- Docker Hub's website search (undocumented: only when its setting is on) -------------------------------------------
def hub_website(http: Http, term: str) -> list[Found]:
    data = _dict(http.get_json(f"{HUB}/api/search/v4?query={_q(term)}&from=0&size=25"), "Docker Hub's website search")
    out = []
    for r in data.get("results") or []:
        if not isinstance(r, dict):
            continue
        kind = str(r.get("type") or "image")
        types = r.get("content_types")
        if kind not in ("image", "dhi") or (isinstance(types, list) and types and "image" not in types):
            continue  # Engine plugins and Desktop extensions are no images to run
        ref = canonical(str(r.get("id") or r.get("name") or ""))
        badge = str(r.get("badge") or "")
        f = Found(ref=ref, name=shown(ref), description=str(r.get("short_description") or "").strip(),
                  publisher=str((r.get("publisher") or {}).get("name") or ""), official=badge == "official",
                  verified=badge == "verified_publisher", open_source=badge == "open_source", stars=number(r.get("star_count")),
                  pulls=number(r.get("raw_pull_count")), updated=epoch(r.get("updated_at")), archived=bool(r.get("archived")),
                  categories=tuple(str(c.get("name")) for c in r.get("categories") or [] if isinstance(c, dict) and c.get("name")),
                  page=hub_page(ref), sources=("hub-website",), terms=(term,))
        if badge == "hardened" or kind == "dhi":
            f.needs_login = "a Docker Hardened Image: pulled from dhi.io after signing in with a Docker account"
        out.append(f)
    return out


# -- Quay.io (documented API) ------------------------------------------------------------------------------------------
def quay_search(http: Http, term: str) -> list[Found]:
    """Quay's search: one substring of a repository's name or description (no '/', no spaces), public ones only."""
    word = re.sub(r"[^\w.-]+", "", str(term).lower()).lstrip("-.")
    if not word:
        return []
    data = _dict(http.get_json(f"{QUAY}/api/v1/find/repositories?query={_q(word)}&page=1&includeUsage=true"), "Quay")
    out = []
    for r in data.get("results") or []:
        if not isinstance(r, dict) or r.get("kind") not in (None, "repository") or r.get("is_public") is False:
            continue
        ns = (r.get("namespace") or {}).get("name") if isinstance(r.get("namespace"), dict) else r.get("namespace")
        name = str(r.get("name") or "")
        if not ns or not name:
            continue
        ref = canonical(f"quay.io/{ns}/{name}")
        out.append(Found(ref=ref, name=ref, description=first_line(str(r.get("description") or "")), publisher=str(ns),
                         stars=number(r.get("stars")), popularity=r.get("popularity") if isinstance(r.get("popularity"), (int, float)) else None,
                         updated=epoch(r.get("last_modified")), page=f"{QUAY}/repository/{ns}/{name}", sources=("quay",),
                         terms=(word,)))
    return out


def quay_tags(http: Http, ref: str, n: int = 10) -> list[dict]:
    path = ref[len("quay.io/"):]
    data = _dict(http.get_json(f"{QUAY}/api/v1/repository/{path}/tag/?onlyActiveTags=true&limit={int(n)}", DETAIL_TTL_S), "Quay's tags")
    return [{"name": str(t["name"]), "updated": epoch(t.get("start_ts") or t.get("last_modified")), "size": number(t.get("size")),
             "platforms": [], "active": True, "digest": str(t.get("manifest_digest") or "")}
            for t in data.get("tags") or [] if isinstance(t, dict) and t.get("name")]


# -- Artifact Hub (documented API) --------------------------------------------------------------------------------------
def artifacthub_search(http: Http, query: str) -> list[Found]:
    """Artifact Hub's container-image packages (kind 12) for `query` (words ORed)."""
    if not query:
        return []
    data = _dict(http.get_json(f"{ARTIFACTHUB}/api/v1/packages/search?kind=12&ts_query_web={_q(query)}&limit=40&facets=false"),
                 "Artifact Hub")
    out = []
    for p in data.get("packages") or []:
        if not isinstance(p, dict):
            continue
        repo = p.get("repository") or {}
        url = str(repo.get("url") or "")
        ref = canonical(url)
        if not ref or "." not in ref.split("/", 1)[0]:
            continue  # a reference without its registry: not pullable as given
        scan = p.get("security_report_summary") or {}
        said_scan = ", ".join(f"{scan[k]} {k}" for k in ("critical", "high", "medium", "low") if isinstance(scan.get(k), int) and scan[k])
        out.append(Found(ref=ref, name=shown(ref), description=str(p.get("description") or "").strip(),
                         publisher=str(repo.get("organization_display_name") or repo.get("user_alias") or repo.get("display_name") or ""),
                         official=bool(p.get("official") or repo.get("official")), verified=bool(repo.get("verified_publisher")),
                         signed=bool(p.get("signed")), stars=number(p.get("stars")), updated=epoch(p.get("ts")),
                         tag=str(p.get("version") or ""), licence=str(p.get("license") or ""), deprecated=bool(p.get("deprecated")),
                         keywords=tuple(str(k) for k in p.get("keywords") or [] if k),
                         scan=(f"scanned: {said_scan}" if said_scan else ("scanned: no known vulnerabilities" if scan else "")),
                         page=f"{ARTIFACTHUB}/packages/container/{repo.get('name')}/{p.get('normalized_name') or p.get('name')}",
                         sources=("artifact-hub",), terms=(query,),
                         extra={"ah": (str(repo.get("name") or ""), str(p.get("normalized_name") or p.get("name") or ""))}))
    return out


def artifacthub_detail(http: Http, repo_name: str, package: str) -> dict:
    return _dict(http.get_json(f"{ARTIFACTHUB}/api/v1/packages/container/{_q(repo_name)}/{_q(package)}", DETAIL_TTL_S),
                 "Artifact Hub")


# -- any registry's tags (the OCI distribution API, an anonymous token where it asks for one) ---------------------------
def _challenge(header: str) -> dict:
    """A WWW-Authenticate Bearer challenge's realm, service and scope."""
    return {k.lower(): v for k, v in re.findall(r'(\w+)="([^"]*)"', str(header or ""))}


def oci_tags(http: Http, ref: str, n: int = 100) -> list[str]:
    """The tags of a public image on its own registry (GHCR, a project's own, any): asked anonymously, with a token when
    the registry asks for one (its realm and service, the scope this image's pull)."""
    host, _, path = ref.partition("/")
    if host == "docker.io":
        host = "registry-1.docker.io"
    url = f"https://{host}/v2/{path}/tags/list?n={int(n)}"
    status, got, body = http.request("GET", url)
    if status == 401:
        c = _challenge(got.get("www-authenticate"))
        realm = c.get("realm", "")
        if not realm.startswith("https://"):
            raise SourceError(f"{host} asks for a sign-in this plugin cannot give")
        token_url = f"{realm}?service={_q(c.get('service', host))}&scope={_q(f'repository:{path}:pull')}"
        status_t, _, tbody = http.request("GET", token_url)
        if status_t != 200:
            raise SourceError(f"{host} gave no anonymous token ({status_t}): the image may be private")
        try:
            tok = json.loads(tbody.decode("utf-8", "replace"))
            token = (tok.get("token") or tok.get("access_token")) if isinstance(tok, dict) else None
        except ValueError:
            token = None
        if not token:
            raise SourceError(f"{host} gave no anonymous token")
        status, got, body = http.request("GET", url, {"Authorization": f"Bearer {token}"})
    if status != 200:
        raise SourceError(f"{host} answered {status} for {path}'s tags")
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        raise SourceError(f"{host} answered something that is not JSON") from None
    return [str(t) for t in (data.get("tags") or []) if t] if isinstance(data, dict) else []


# -- Docker Hub's pull allowance (its documented check: a HEAD, which spends no pull) -----------------------------------
def hub_allowance(http: Http) -> dict | None:
    """Docker Hub's anonymous pulls left from this network's address ({limit, left, hours}); None when it says nothing.
    Its answer also names the address asking: never kept, never said."""
    status, _, body = http.request("GET", f"{DOCKER_AUTH}/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull")
    if status != 200:
        return None
    try:
        got = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    token = got.get("token") if isinstance(got, dict) else None
    if not token:
        return None
    status, got, _ = http.request("HEAD", f"{DOCKER_REGISTRY}/v2/ratelimitpreview/test/manifests/latest",
                                  {"Authorization": f"Bearer {token}"})
    limit, left = got.get("ratelimit-limit") or "", got.get("ratelimit-remaining") or ""
    m1, m2 = re.match(r"\s*(\d+)\s*;\s*w=(\d+)", limit), re.match(r"\s*(\d+)", left)
    if not m1 or not m2:
        return None
    return {"limit": int(m1.group(1)), "left": int(m2.group(1)), "hours": round(int(m1.group(2)) / 3600, 1)}
