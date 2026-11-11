"""The image search (0.2.0; the user, 2026-11-10: "lets roll in a way to import docker images (from various docker repos)
with a search that can find things like nginx webserver or postfix secure file server w/ all the anti-spam+++"; "there
needs to be enough docker description in order to understand what is being provided"; "i want to be able to get a docker
image for anything"). A search's words read; each source answering as its API did on 2026-11-11 (stand-ins of that shape:
Docker Hub through the engine's `docker search`, Docker Hub's repository and tags API, Quay, Artifact Hub, an anonymous
registry token); merged and ranked: the user's two searches put a whole mail server and the official nginx first, a relay
and an ingress controller below them with the reason said; anything else goes by its own words. Nothing is pulled unless
asked, nothing reached, nothing started."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

import pytest

import plugin_platform_docker as dk
import plugin_platform_docker.__main__ as cli
from liminal_libs.machines.wsl import Wsl
from plugin_platform_docker import DockerPlugin, catalog, query, search, sources
from plugin_platform_docker.sources import Http, canonical, plain
from test_plugin import Docker, FakeEngine, FakeWsl, Ubuntu

NOW = 1_794_400_000.0  # the wall the ranking's "updated" is read against (2026-11-11)
DAY = 86400.0
IP = "203.0.113.9"  # what Docker Hub's answers echo of the asker: never kept, never said


def iso(days: float) -> str:
    return datetime.fromtimestamp(NOW - days * DAY, timezone.utc).isoformat().replace("+00:00", "Z")


def hub(name, description, stars, official=False):
    """A row as `docker search --format "{{json .}}"` prints it (its values strings, [OK] for an official image)."""
    return {"Description": description, "IsAutomated": "", "IsOfficial": "[OK]" if official else "", "Name": name, "StarCount": str(stars)}


HUB_SEARCH = {
    "postfix": [hub("boky/postfix", "Simple SMTP relay (postfix null client): send-only, for apps that need to send email", 185),
                hub("mailcow/postfix", "", 21)],
    "mailserver": [hub("mailserver/docker-mailserver", "A fullstack but simple mail server with SMTP, IMAP, LDAP, Antispam, Antivirus, etc.", 268),
                   hub("onlyoffice/mailserver", "Full-featured mail server solution developed on the base of the iRedMail", 40),
                   hub("spammer/freemail", "postfix mail server antispam antivirus dkim imap free best", 0)],
    "antispam": [hub("rspamd/rspamd", "Rspamd: a fast, free and open-source spam filtering system", 60)],
    "nginx": [hub("nginx/nginx-ingress", "NGINX and NGINX Plus Ingress Controllers for Kubernetes", 110),
              hub("nginx", "Official build of Nginx.", 21419, official=True),
              hub("nginx/nginx-prometheus-exporter", "NGINX Prometheus Exporter for NGINX and NGINX Plus", 45),
              hub("nginx/nginx-unprivileged", "Unprivileged NGINX Dockerfiles", 2)],
    "webserver": [hub("someone/tiny-webserver", "a tiny static webserver", 3)],
    "home assistant": [hub("homeassistant/home-assistant", "Open source home automation that puts local control and privacy first.", 2400),
                       hub("someone/assistant-bot", "a chat assistant", 1)],
}
HUB_REPOS = {
    "mailserver/docker-mailserver": {
        "pull_count": 12676361, "star_count": 268, "last_updated": iso(1), "status_description": "active",
        "description": "A fullstack but simple mail server with SMTP, IMAP, LDAP, Antispam, Antivirus, etc.",
        "categories": [{"name": "Security", "slug": "security"}],
        "full_description": ("# docker-mailserver\n\n<p align=\"center\"><img src=\"https://example.invalid/logo.png\"></p>\n"
                             "A production-ready fullstack but simple mail server (SMTP, IMAP, LDAP, Antispam, Antivirus, etc.).\n\n"
                             "![badge](https://example.invalid/badge.svg)\n[Documentation](https://example.invalid/docs)\n\n"
                             "```sh\ndocker run --rm mailserver/docker-mailserver\n```\n- Postfix\n- Dovecot\n")},
    "library/nginx": {"pull_count": 13573379546, "star_count": 21419, "last_updated": iso(0.5), "categories": [{"name": "Web servers"}],
                      "full_description": "# Quick reference\n\nMaintained by: the NGINX Docker Maintainers"},
    "nginx/nginx-ingress": {"pull_count": 1_000_000_000, "star_count": 110, "last_updated": iso(3), "categories": [{"name": "Networking"}]},
    "nginx/nginx-prometheus-exporter": {"pull_count": 100_000_000, "star_count": 45, "last_updated": iso(20)},
    "nginx/nginx-unprivileged": {"pull_count": 150_000, "star_count": 2, "last_updated": iso(2)},
    "boky/postfix": {"pull_count": 50_000_000, "star_count": 185, "last_updated": iso(30)},
    "mailcow/postfix": {"pull_count": 10_000_000, "star_count": 21, "last_updated": iso(400)},
    "onlyoffice/mailserver": {"pull_count": 447_005, "star_count": 40, "last_updated": iso(190)},
    "spammer/freemail": {"pull_count": 0, "star_count": 0, "last_updated": iso(10)},
    "homeassistant/home-assistant": {"pull_count": 900_000_000, "star_count": 2400, "last_updated": iso(1)},
}
DEFAULT_REPO = {"pull_count": 1000, "star_count": 1, "last_updated": iso(100)}
TAGS = {
    "mailserver/docker-mailserver": {"count": 74, "results": [
        {"name": "17.0.0", "last_updated": iso(6), "full_size": 312_000_000, "tag_status": "active", "digest": "sha256:aa",
         "images": [{"os": "linux", "architecture": "amd64"}, {"os": "linux", "architecture": "arm64"}, {"os": "unknown", "architecture": "unknown"}]},
        {"name": "17", "last_updated": iso(6), "full_size": 312_000_000, "tag_status": "active", "images": [{"os": "linux", "architecture": "amd64"}]},
        {"name": "latest", "last_updated": iso(6), "full_size": 312_000_000, "tag_status": "active", "images": []}]},
    "spammer/freemail": {"count": 0, "results": []},  # a repository with no image: how spam looks
}
DEFAULT_TAGS = {"count": 3, "results": [{"name": "latest", "last_updated": iso(9), "full_size": 50_000_000, "images": []}]}
QUAY = {
    "postfix": [{"kind": "repository", "namespace": {"name": "panubo"}, "name": "postfix", "description": "Postfix SMTP relay",
                 "is_public": True, "last_modified": NOW - 20 * DAY, "stars": 3, "popularity": 4.0}],
    "mailserver": [{"kind": "repository", "namespace": {"name": "apollobusinessautomation"}, "name": "docker-mailserver",
                    "description": "a mirror", "is_public": True, "last_modified": NOW - 300 * DAY, "stars": 0, "popularity": 0.0}],
    "nginx": [{"kind": "repository", "namespace": {"name": "nginx"}, "name": "nginx-unprivileged", "description": "Unprivileged NGINX Dockerfiles",
               "is_public": True, "last_modified": NOW - 2 * DAY, "stars": 4, "popularity": 50.0}],
}
AH_POSTFIX = [{"name": "postfix", "normalized_name": "postfix", "description": "Postfix mail transfer agent", "version": "latest",
               "repository": {"url": "oci://registry.opensuse.org/opensuse/postfix", "name": "opensuse-postfix",
                              "verified_publisher": True, "official": True, "organization_display_name": "openSUSE"},
               "signed": True, "security_report_summary": {"critical": 0, "high": 1}, "stars": 2, "ts": NOW - 5 * DAY,
               "license": "IPL-1.0"}]
SYFT = [{"name": "syft", "normalized_name": "syft", "description": "CLI tool and library for generating a Software Bill of Materials from "
         "container images and filesystems", "version": "v1.40.0", "repository": {"url": "oci://ghcr.io/anchore/syft", "name": "anchore-syft",
         "verified_publisher": True, "organization_display_name": "Anchore"}, "stars": 50, "ts": NOW - 1 * DAY, "license": "Apache-2.0"}]


class Registries:
    """The registries' answers as the opener's stand-in: (status, headers, body) by address; every request kept."""

    def __init__(self):
        self.asked: list[tuple[str, str, dict]] = []
        self.quay_busy = False
        self.missing: set[str] = set()

    def hosts(self) -> list[str]:
        return [urllib.parse.urlsplit(u).hostname for _, u, _ in self.asked]

    def __call__(self, method, url, headers, timeout):
        self.asked.append((method, url, dict(headers)))
        u = urllib.parse.urlsplit(url)
        q = urllib.parse.parse_qs(u.query)
        ok = lambda data, extra=None: (200, {"x-ratelimit-ip": IP, **(extra or {})}, json.dumps(data).encode())  # noqa: E731
        if u.hostname == "hub.docker.com" and u.path.startswith("/v2/namespaces/"):
            parts = u.path.split("/")
            key = f"{parts[3]}/{parts[5]}"
            if key in self.missing:
                return 404, {}, b'{"message": "object not found"}'
            return ok(TAGS.get(key, DEFAULT_TAGS) if len(parts) > 6 and parts[6] == "tags" else HUB_REPOS.get(key, DEFAULT_REPO))
        if u.hostname == "hub.docker.com" and u.path == "/api/search/v4":
            return ok({"total": 1, "results": [{"id": "dhi/nginx", "name": "dhi/nginx", "type": "dhi", "badge": "hardened",
                                                "short_description": "a hardened nginx", "publisher": {"name": "Docker"},
                                                "star_count": 9, "raw_pull_count": 5_000_000, "updated_at": iso(0),
                                                "content_types": ["image"], "categories": []}]})
        if u.hostname == "quay.io" and u.path == "/api/v1/find/repositories":
            if self.quay_busy:
                return 429, {"retry-after": "120"}, b""
            return ok({"results": QUAY.get(q["query"][0], []), "has_additional": False, "page": 1})
        if u.hostname == "artifacthub.io" and u.path == "/api/v1/packages/search":
            words = q["ts_query_web"][0].split(" or ")
            return ok({"packages": (AH_POSTFIX if "postfix" in words else []) + (SYFT if "file" in words else [])})
        if u.hostname == "auth.docker.io":
            return ok({"token": "anonymous-token"})
        if u.hostname == "registry-1.docker.io" and method == "HEAD":
            return 200, {"ratelimit-limit": "100;w=3600", "ratelimit-remaining": "97;w=3600", "docker-ratelimit-source": IP}, b""
        if u.hostname == "ghcr.io" and u.path == "/token":
            return ok({"token": "ghcr-anonymous"})
        if u.hostname == "ghcr.io" and u.path.endswith("/tags/list"):
            if headers.get("Authorization") != "Bearer ghcr-anonymous":
                return 401, {"www-authenticate": 'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:user/image:pull"'}, b""
            return ok({"name": "linuxserver/swag", "tags": ["5.9.0-ls498", "5.10.0-ls499", "latest"]})
        return 404, {}, b""


class SearchEngine:
    """An engine as the search asks it (`rows` of `docker search`)."""

    def __init__(self, answers=None):
        self.answers = HUB_SEARCH if answers is None else answers
        self.asked: list[tuple] = []

    def rows(self, *args, timeout=None):
        self.asked.append(args)
        assert args[:4] == ("search", "--no-trunc", "--limit", "40") and timeout == sources.ENGINE_SEARCH_S
        return [dict(r) for r in self.answers.get(args[4], [])]


def searcher(reg=None):
    reg = reg or Registries()
    return search.Searcher(Http(opener=reg, sleep=lambda s: None), wall=lambda: NOW), reg


def refs(outcome) -> list[str]:
    return [r.found.ref for r in outcome.results]


# -- reading a search ---------------------------------------------------------------------------------------------------
def test_a_search_is_read_as_roles_products_features_and_the_users_other_words():
    q = query.parse("postfix secure file server w/ all the anti-spam+++")
    assert (q.concepts, q.words, q.roles) == (("postfix", "secure", "antispam"), ("file", "server"), ("mailserver",))
    assert q.said() == "a mail server · Postfix · secure · anti-spam; other words: file, server"
    assert query.hub_terms(q) == ["postfix", "mailserver", "antispam"]  # Docker Hub's budget: three
    assert query.quay_terms(q) == ["postfix", "mailserver", "antispam"] and query.artifacthub_query(q) == "postfix or mail or antispam or file"
    q = query.parse("nginx webserver")
    assert (q.concepts, q.words, q.roles, query.hub_terms(q)) == (("nginx", "webserver"), (), ("webserver",), ["nginx", "webserver"])
    q = query.parse("Home Assistant")  # anything: its own words, as typed
    assert (q.concepts, q.words, q.roles) == ((), ("home", "assistant"), ()) and query.hub_terms(q)[0] == "home assistant"
    assert query.parse("a reverse proxy with let's encrypt").concepts == ("proxy", "tls")
    assert query.parse("web-server").concepts == ("webserver",) and query.parse("anti spam").concepts == ("antispam",)
    assert query.parse("the docker image please").empty and query.parse("x" * 900).text == "x" * query.MAX_CHARS
    mail = {p.name for p in query.picks_for(query.parse("postfix anti-spam"), catalog.PICKS)}
    assert "docker-mailserver" in mail and "nginx" not in mail and {p.name for p in query.picks_for(query.parse("swag"), catalog.PICKS)} == {
        "SWAG (Secure Web Application Gateway)"}


def test_references_are_one_name_wherever_they_come_from():
    assert canonical("nginx") == canonical("docker.io/library/nginx:1.27") == canonical("index.docker.io/library/nginx") == "docker.io/library/nginx"
    assert canonical("oci://registry-1.docker.io/mailserver/docker-mailserver") == "docker.io/mailserver/docker-mailserver"
    assert canonical("lscr.io/linuxserver/swag:latest") == "ghcr.io/linuxserver/swag"
    assert canonical("localhost:5000/team/app:1@sha256:00") == "localhost:5000/team/app" and canonical("") == ""
    assert sources.pull_ref("docker.io/library/nginx", "stable") == "nginx:stable" and sources.pull_ref("quay.io/a/b", "") == "quay.io/a/b:latest"
    assert sources.hub_page("docker.io/library/nginx").endswith("/_/nginx") and sources.registry_of("ghcr.io/x/y") == "GitHub (ghcr.io)"


def test_a_publishers_readme_is_shown_as_its_words_only():
    md = ("<!-- hidden -->\n# Title\n<p align=center><img src=x.png></p>\nText with **bold**, `code` and a [link](https://x.invalid/a).\n"
          "![image](https://x.invalid/i.png)\n```\nrm -rf /\n```\n| a | b |\n|---|---|\n- item")
    assert plain(md) == ["Title", "Text with bold, code and a link.", "a | b", "item"]
    by_reference = ("[![ci::status]][ci::github] [![docs][d]][w]\n[ci::status]: https://img.example.invalid/x.svg\n"
                    "[ci::github]: https://github.example.invalid/x\nThe [documentation][documentation::web] is hosted there.")
    assert plain(by_reference) == ["The documentation is hosted there."]  # docker-mailserver's README begins so
    assert len(plain("\n".join(f"line {n}" for n in range(100)))) == sources.README_LINES


# -- the user's two searches --------------------------------------------------------------------------------------------
def test_the_users_mail_search_puts_a_whole_mail_server_first_and_says_why():
    s, reg = searcher()
    engine = SearchEngine()
    out = s.search("postfix secure file server w/ all the anti-spam+++", engine=engine, engine_name="wsl-ubuntu")
    assert [a[4] for a in engine.asked] == ["postfix", "mailserver", "antispam"]
    top = out.results[0]
    assert top.found.ref == "docker.io/mailserver/docker-mailserver" and top.found.tag == "17"  # the pick's advice
    assert top.reasons[:3] == ("sponsored open source", "covers Postfix, anti-spam", "Liminal's pick for a mail server")  # "server": weak
    stalwart = out.result("docker.io/stalwartlabs/stalwart")  # its own words say "not Postfix": a pick's concepts decide
    assert "covers anti-spam" in stalwart.reasons and not any("Postfix" in r for r in stalwart.reasons if r.startswith("covers"))
    assert refs(out).index("docker.io/stalwartlabs/stalwart") > refs(out).index("github.com/mailu/mailu")  # Postfix asked: Postfix first
    assert top.found.pulls == 12676361 and top.found.provides.startswith("a complete mail server in one image: Postfix")
    order = refs(out)
    relay = order.index("docker.io/boky/postfix")
    assert relay > order.index("github.com/mailcow/mailcow-dockerized") and relay > order.index("docker.io/stalwartlabs/stalwart")
    assert "a relay or a test catcher, not a whole mail server" in out.results[relay].reasons
    assert "docker.io/spammer/freemail" not in order  # it holds no image (no tag): left out, and said
    assert out.notes == ["1 Docker Hub repository left out: no image in it (no tag)"]
    stack = out.result("github.com/mailcow/mailcow-dockerized")
    assert stack.found.stack and "a compose stack of several images: installed its own way, not one pull" in stack.reasons
    iredmail = order.index("docker.io/iredmail/mariadb")
    assert iredmail > order.index("docker.io/mailserver/docker-mailserver") and any("abandoned" in r for r in out.results[iredmail].reasons)
    syft = out.result("ghcr.io/anchore/syft")  # found by "file" alone (its "filesystems"): no mail server, below even the relay
    assert "matches only the search's other words (file)" in syft.reasons and order.index("ghcr.io/anchore/syft") > relay
    suse = out.result("registry.opensuse.org/opensuse/postfix")
    assert suse.found.verified and suse.found.signed and suse.found.scan == "scanned: 1 high"
    assert out.asked["docker-hub"]["found"] == 6 and out.asked["quay"]["terms"] == ["postfix", "mailserver", "antispam"]
    assert out.allowance == {"limit": 100, "left": 97, "hours": 1.0} and IP not in json.dumps(out.allowance)


def test_nginx_webserver_puts_the_official_nginx_first_and_kubernetes_parts_below():
    s, _ = searcher()
    out = s.search("nginx webserver", engine=SearchEngine(), engine_name="wsl-ubuntu")
    assert refs(out)[:2] == ["docker.io/library/nginx", "docker.io/nginx/nginx-unprivileged"]
    first = out.results[0]
    assert first.found.tag == "stable" and first.reasons[0] == "Docker Official Image" and "13.6B pulls" in first.reasons
    unpriv = out.results[1].found
    assert unpriv.sources == ("catalog", "quay", "docker-hub") or set(unpriv.sources) == {"catalog", "quay", "docker-hub"}  # one image, three sources
    ingress = out.result("nginx/nginx-ingress")
    assert "made for Kubernetes or monitoring, not a server to run" in ingress.reasons
    assert refs(out).index("docker.io/nginx/nginx-ingress") > refs(out).index("docker.io/library/caddy")


def test_anything_else_goes_by_its_own_words():
    s, _ = searcher()
    out = s.search("home assistant", engine=SearchEngine())
    assert refs(out)[0] == "docker.io/homeassistant/home-assistant" and out.results[0].covers == ("home", "assistant")
    assert out.asked["catalog"]["found"] == 0 and not any(r.found.pick for r in out.results)
    with pytest.raises(ValueError, match="nothing to search for"):
        s.search("   docker image   ")


def test_without_an_engine_docker_hub_is_said_and_the_rest_answer():
    s, reg = searcher()
    out = s.search("postfix anti-spam", engine=None)
    assert out.asked["docker-hub"]["error"].startswith("not searched: no Docker engine answers")
    assert "docker.io/mailserver/docker-mailserver" in refs(out) and out.asked["quay"]["found"] == 2 and out.engine == ""
    only = s.search("postfix", where="quay", engine=SearchEngine())
    assert set(only.asked) == {"quay"}  # Postfix asks for its role too: its word on Quay finds a mirror, ranked below
    assert refs(only) == ["quay.io/panubo/postfix", "quay.io/apollobusinessautomation/docker-mailserver"]


def test_a_registry_that_asks_to_wait_is_left_alone_until_then():
    reg = Registries()
    reg.quay_busy = True
    s, _ = searcher(reg)
    out = s.search("postfix anti-spam", engine=SearchEngine())
    assert out.asked["quay"]["error"] == "quay.io asked to wait (120 s)" and reg.hosts().count("quay.io") == 1
    again = s.search("nginx", engine=SearchEngine())
    assert again.asked["quay"]["error"].startswith("quay.io asked to wait") and reg.hosts().count("quay.io") == 1  # not asked again


def test_every_request_is_https_with_the_plugins_own_agent_cached_and_spaced():
    slept: list[float] = []
    t = [100.0]
    reg = Registries()
    http = Http(opener=reg, sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), clock=lambda: t[0])
    s = search.Searcher(http, wall=lambda: NOW)
    s.search("nginx", engine=SearchEngine())
    for method, url, headers in reg.asked:
        assert url.startswith("https://") and headers["User-Agent"] == sources.USER_AGENT == f"plugin-platform-docker/{dk.__version__}"
        assert set(headers) <= {"User-Agent", "Accept", "Authorization"}  # nothing of the user's
    assert slept and all(x <= max(sources.SPACING.values()) for x in slept)  # each host's turns spaced, never more
    n = len(reg.asked)
    s.search("nginx", engine=SearchEngine())
    assert len(reg.asked) == n + 0 or all(urllib.parse.urlsplit(u).hostname in ("auth.docker.io", "registry-1.docker.io")
                                          for _, u, _ in reg.asked[n:])  # the same search: from what was kept
    with pytest.raises(sources.SourceError, match="not an https address"):
        http.request("GET", "http://hub.docker.com/v2/")


def test_details_say_what_an_image_is_and_holds():
    s, reg = searcher()
    out = s.search("postfix anti-spam", engine=SearchEngine())
    title, lines = s.details("mailserver/docker-mailserver", out)
    assert title == "Details of docker-mailserver (Docker Hub)"  # its name as written: lower case
    assert lines[0] == "Where: Docker Hub · mailserver/docker-mailserver · by mailserver"
    assert any(x.startswith("What it provides: a complete mail server in one image: Postfix (Postscreen, DNSBL), Dovecot") for x in lines)
    assert "Categories: Security" in lines and "Licence: MIT" in lines
    assert "Tags: 74 in all · 12.7M pulls · 268 stars" in lines
    assert "  17.0.0 · 6 days ago · 312 MB · linux/amd64, linux/arm64" in lines  # the unknown platform left out
    readme = lines[lines.index("Its README (the publisher's words, first lines):") + 1:]
    assert readme[:4] == ["  docker-mailserver", "  A production-ready fullstack but simple mail server (SMTP, IMAP, LDAP, Antispam, Antivirus, etc.).",
                          "  Documentation", "  Postfix"]  # no image, no link address, no command block
    assert lines[-1] == "Pulled as: mailserver/docker-mailserver:17"
    title, lines = s.details("lscr.io/linuxserver/swag")  # GHCR, with the anonymous token it asks for
    at = lines.index("Tags (as its registry lists them, not by date):")  # no dates there: not called the newest
    assert lines[at + 1] == "  5.9.0-ls498, 5.10.0-ls499, latest" and lines[-1] == "Pulled as: ghcr.io/linuxserver/swag:latest"
    token = [u for _, u, _ in reg.asked if u.startswith("https://ghcr.io/token")]
    assert token == ["https://ghcr.io/token?service=ghcr.io&scope=repository%3Alinuxserver%2Fswag%3Apull"]
    title, lines = s.details("github.com/mailcow/mailcow-dockerized")
    assert "Installed as a compose stack, not one pull: https://docs.mailcow.email/getstarted/install/" in lines
    assert not any(x.startswith("Pulled as") for x in lines)


# -- on the platform's page ---------------------------------------------------------------------------------------------
class Login:
    """The login the platform lends the plugin, as far as its one setting goes."""

    def __init__(self, website=""):
        self.website = website

    def variables(self, names):
        return {dk.WEBSITE_VAR: self.website} if self.website else {}


def page_plugin(state="Running", website=""):
    engine = FakeEngine()
    engine.search = HUB_SEARCH
    wsl = FakeWsl(state=state)
    ubuntu = Ubuntu(wsl=Wsl(runner=wsl))
    run = Docker(wsl=engine)
    reg = Registries()
    p = DockerPlugin(machines=[ubuntu], wsl=Wsl(runner=wsl), runner=run, streamer=run.stream, env={},
                     http=Http(opener=reg, sleep=lambda s: None), wall=lambda: NOW)
    p.login = Login(website)
    return p, engine, reg


def test_the_page_gets_a_search_box_the_results_described_details_and_a_pull_that_is_a_job():
    p, engine, reg = page_plugin()
    s = p.status()
    found = s["tables"][0]
    assert found["title"] == "Find an image" and found["rows"] == [] and found["search"]["form"] == "search"
    assert [f["id"] for f in s["forms"]][:2] == ["search", "details"]
    answer = p.ask("search", "nginx webserver", "all")
    assert answer["said"] == "9 images for “nginx webserver”: the table below lists them" and answer["lines"][0] == "read as: a web server · nginx"
    s = p.status()
    found = s["tables"][0]
    assert found["title"] == "Find an image: 9 for “nginx webserver”" and found["search"]["value"] == "nginx webserver"
    assert found["note"].startswith("Read as: a web server · nginx. · Docker Hub through wsl-ubuntu: 5 found (nginx, webserver)")
    assert "Docker Hub's anonymous pulls left from here: 97 of 100 (per 1 hour)" in found["note"] and IP not in json.dumps(s)
    first = found["rows"][0]
    assert first[0] == {"text": "nginx", "sub": "Docker Hub · Docker Official Images"}
    assert first[1]["text"].startswith("nginx: web server, reverse proxy") and first[1]["sub"] == "Web servers · BSD-2-Clause"
    assert first[3] == {"form": "detail", "title": "Details", "values": {"image": "docker.io/library/nginx"}, "label": "Details of nginx"}
    assert first[4] == {"form": "pull", "title": "Pull…", "values": {"image": "nginx:stable"}, "label": "Pull nginx:stable on wsl-ubuntu",
                        "note": "nginx:stable on wsl-ubuntu"}
    pull = next(f for f in s["forms"] if f["id"] == "pull")
    assert pull["job"] is True and dk.DockerPlugin.JOB_HOOKS == ("pull",)
    assert not any(a[0] == "pull" for a in engine.asked)  # a search pulls nothing
    shown = p.ask("details", "nginx")
    assert shown["said"] == "Details of nginx (Docker Hub)" and "Pulled as: nginx:stable" in shown["lines"]
    detail = next(f for f in s["forms"] if f["id"] == "detail")  # a row's own: its image fixed, asked as it opens
    assert detail["confirm"] is False and detail["fields"] == [{"name": "image", "label": "Image", "type": "fixed"}]
    lines: list[str] = []
    done = p.pull("wsl-ubuntu", "nginx:stable", log=lines.append)  # as the platform runs it: a job, its lines as they come
    assert lines[0] == "pulling nginx:stable on wsl-ubuntu (Docker in Liminal-Ubuntu under WSL 2)"
    assert lines[1:] == [x for x in FakeEngine().answer(["pull", "nginx:stable"])[1].splitlines() if x.strip()]
    assert done["said"] == "nginx:stable pulled on wsl-ubuntu" and ["pull", "nginx:stable"] in engine.asked
    assert p.ask("clear_search")["said"] == "the search's results forgotten" and p.status()["tables"][0]["rows"] == []
    json.dumps(s)


def test_a_compose_stack_is_listed_never_pulled():
    p, engine, _ = page_plugin()
    p.ask("search", "mailcow")
    row = next(r for r in p.status()["tables"][0]["rows"] if r[0]["text"] == "mailcow: dockerized")
    assert row[4] == {"text": "a stack", "sub": "installed its own way"}
    with pytest.raises(ValueError, match="mailcow: dockerized is a compose stack of several images, not one to pull"):
        p.pull("wsl-ubuntu", "github.com/mailcow/mailcow-dockerized")
    assert not any(a[0] == "pull" for a in engine.asked)


def test_with_no_engine_answering_the_search_still_answers_and_no_pull_is_offered():
    p, engine, reg = page_plugin(state="Stopped")
    p.ask("search", "postfix anti-spam")
    s = p.status()
    found = s["tables"][0]
    assert "Docker Hub: not searched: no Docker engine answers" in found["note"]
    assert all(r[4] in ({"text": "–", "sub": "no engine answers"}, {"text": "a stack", "sub": "installed its own way"}) for r in found["rows"])
    assert not any(f["id"] == "pull" for f in s["forms"]) and engine.asked == []  # the stopped distribution never asked


def test_docker_hubs_website_search_only_when_its_setting_is_on():
    p, _, reg = page_plugin()
    p.ask("search", "nginx")
    assert not any(u.startswith("https://hub.docker.com/api/search/") for _, u, _ in reg.asked)  # off unless set: undocumented
    q, _, reg = page_plugin(website="on")
    q.ask("search", "nginx")
    assert any(u.startswith("https://hub.docker.com/api/search/v4?query=nginx") for _, u, _ in reg.asked)
    dhi = next(r for r in q.status()["tables"][0]["rows"] if r[0]["text"] == "dhi/nginx")
    assert "needs a sign-in to pull" in dhi[2]["sub"]
    assert dk.DockerPlugin.keys[0].name == dk.WEBSITE_VAR and dk.DockerPlugin.keys[0].secret is False


def test_detached_the_results_and_what_the_registries_said_are_forgotten():
    p, _, reg = page_plugin()
    p.ask("search", "nginx")
    p.detach()
    assert p._rt.found is None and p._rt.searcher is None


def test_the_command_line_searches_and_shows_details(monkeypatch, capsys):
    p, _, _ = page_plugin()
    monkeypatch.setattr(cli, "MACHINE", p)
    assert cli.main(["search", "nginx", "webserver", "--where", "all"]) == 0
    out = capsys.readouterr().out
    assert "9 images for “nginx webserver”" in out and " 1. nginx (Docker Hub · Docker Official Images)" in out
    assert cli.main(["details", "nginx"]) == 0 and "Pulled as: nginx:stable" in capsys.readouterr().out


def test_the_versions_agree():
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert dk.__version__ == sources.VERSION == project["project"]["version"]


# -- what a review of 0.2.0 found, mended (2026-11-11) -------------------------------------------------------------------
def test_a_search_never_starts_a_distribution_stopped_since_the_last_look():
    """The engine is asked as every change asks it: WSL's list read again at the search, a distribution stopped since the
    last look (30 s are kept) said as not running, no `wsl -d` at all."""
    t = [1000.0]
    engine = FakeEngine()
    engine.search = HUB_SEARCH
    wsl = FakeWsl(state="Running")
    run = Docker(wsl=engine)
    p = DockerPlugin(machines=[Ubuntu(wsl=Wsl(runner=wsl))], wsl=Wsl(runner=wsl), runner=run, streamer=run.stream, env={},
                     http=Http(opener=Registries(), sleep=lambda s: None), wall=lambda: NOW, clock=lambda: t[0])
    p.login = Login()
    p.status()  # read while it runs
    wsl.state = "Stopped"
    t[0] += 5
    before = len(wsl.calls)
    p.ask("search", "nginx webserver")
    assert not any(c[:2] == ["wsl", "-d"] for c in wsl.calls[before:])  # nothing booted
    assert not any(a[0] == "search" for a in engine.asked)
    assert "Docker Hub: not searched: no Docker engine answers" in p.status()["tables"][0]["note"]


def test_the_tag_offered_is_latest_when_there_and_never_a_signature_or_a_development_build():
    assert sources.tag_to_offer(["sha256-1f2e3d.sig", "dev", "2026.11.0b3", "2026.10.4", "2026.10.3"]) == "2026.10.4"
    assert sources.tag_to_offer(["sha256-1f2e3d.sig", "nightly-2026-11-11"]) == "nightly-2026-11-11"  # only that: it, not the signature
    assert sources.tag_to_offer(["sha256-1f2e3d.sig", "sha256-aa.att"]) == ""
    reg = Registries()
    many = {"count": 1400, "results": [{"name": f"13.{n}-alpine3.22", "last_updated": iso(1), "images": []} for n in range(10)]}
    TAGS["library/postgres"] = many
    HUB_SEARCH_PG = {"postgres": [hub("postgres", "The PostgreSQL object-relational database system", 14000, official=True)]}
    try:
        s, _ = searcher(reg)
        out = s.search("postgres", engine=SearchEngine(HUB_SEARCH_PG))
        assert out.result("postgres").found.tag == "latest"  # not on the newest page, asked by its name: there (the stand-in's 200)
        asked = [u for _, u, _ in reg.asked if "/tags/latest" in u]
        assert asked == ["https://hub.docker.com/v2/namespaces/library/repositories/postgres/tags/latest"]
    finally:
        del TAGS["library/postgres"]


def test_redirects_are_followed_only_to_https_on_the_same_host_and_answers_are_bounded():
    import urllib.request

    h = sources._SameHostHttps()
    req = urllib.request.Request("https://hub.docker.com/v2/x", headers={"Authorization": "Bearer t"})
    assert h.redirect_request(req, None, 302, "Found", {}, "http://hub.docker.com/v2/x") is None  # in the clear: not followed
    assert h.redirect_request(req, None, 302, "Found", {}, "https://elsewhere.example/v2/x") is None  # another host: not followed
    assert h.redirect_request(req, None, 301, "Moved", {}, "https://hub.docker.com/v2/y").full_url == "https://hub.docker.com/v2/y"

    class Drip:  # a registry feeding its answer a byte at a time
        def read(self, n):
            return b"x"
    with pytest.raises(sources.SourceError, match="took more than"):
        sources._read_all(Drip(), deadline=0.0)
    big = Http(opener=lambda m, u, h, t: (200, {}, b"x" * (sources.MAX_BYTES + 1)), sleep=lambda s: None)
    with pytest.raises(sources.SourceError, match="more than 4 MB"):
        big.get_json("https://quay.io/api/v1/find/repositories?query=x")
    import http.client

    def broken(method, url, headers, timeout):
        raise http.client.IncompleteRead(b"par")
    sources_open = sources._urlopen
    try:  # a broken answer is the source's failure, never the search's
        with pytest.raises(sources.SourceError):
            sources._OPENER.open = lambda *a, **k: (_ for _ in ()).throw(http.client.IncompleteRead(b"par"))
            sources_open("GET", "https://quay.io/x", {}, 1)
    finally:
        del sources._OPENER.open


def test_a_publishers_text_is_read_fast_whatever_it_holds():
    import time as _time

    for nasty in ("[" * 200_000, "![" * 100_000, "<!--" * 100_000, "[x](" * 50_000):
        began = _time.perf_counter()
        plain(nasty)
        assert _time.perf_counter() - began < 1.0, nasty[:8]


def test_a_late_source_stops_at_the_deadline_and_what_it_found_is_kept(monkeypatch):
    import time as _time

    monkeypatch.setattr(search, "DEADLINE_S", 0.3)
    calls = []

    def slow(term):
        calls.append(term)
        if term == "mailserver":
            _time.sleep(0.6)
        return [sources.Found(ref=canonical(f"quay.io/x/{term}"), name=term, sources=("quay",))]
    monkeypatch.setattr(search, "quay_search", lambda http, term: slow(term))
    s, _ = searcher()
    out = s.search("postfix anti-spam", where="quay", engine=None)
    assert out.asked["quay"] == {"terms": ["postfix", "mailserver", "antispam"], "found": 1,
                                 "error": "not every term answered within 0.3 s"}
    assert refs(out) == ["quay.io/x/postfix"]  # the term answered in time: kept
    _time.sleep(0.5)
    assert calls == ["postfix", "mailserver"]  # no term asked after the deadline


def test_a_registry_search_alone_keeps_its_own_reference():
    s, _ = searcher()
    out = s.search("nginx", where="quay")
    assert refs(out) == ["quay.io/nginx/nginx-unprivileged"]  # not turned into the pick's Docker Hub reference


def test_what_a_search_reads_and_asks_for_whatever_is_typed():
    q = query.parse("rspamd")  # a project's own name: asked for by it, its feature understood too, no mail server asked for
    assert q.concepts == ("antispam",) and q.words == ("rspamd",) and q.roles == () and query.hub_terms(q) == ["rspamd", "antispam"]
    assert query.parse("postfix with rspamd").roles == ("mailserver",) and query.parse("anti-spam").roles == ("mailserver",)
    s, _ = searcher()
    out = s.search("rspamd", engine=SearchEngine())
    assert refs(out)[0] == "docker.io/rspamd/rspamd" and not any(r.found.pick for r in out.results)  # the project named, first
    assert query.parse("clamav").roles == ()  # ClamAV is no mail server of its own
    assert query.parse("secure").empty and query.parse("secure rootless").empty
    assert query.parse("café gitea").words == ("café", "gitea")
    for typed in ("--help", "-rf /", "nginx -v", "—— -", "- - -x"):
        q = query.parse(typed)
        terms = [*query.hub_terms(q), *query.quay_terms(q)] if not q.empty else []
        assert not any(t.startswith("-") for t in terms), typed


def test_the_streaming_runner_runs_windowless_gives_each_line_and_is_killed_when_too_long(monkeypatch):
    import io
    import os
    import subprocess

    from plugin_platform_docker import engines as eng

    class Proc:
        def __init__(self, args, **kw):
            Proc.kw, self.returncode, self.killed = kw, None, False
            self.stdout = io.BytesIO(b"a: Pulling fs layer\r\n\r\nStatus: Downloaded\n")
            self.stderr = io.BytesIO(b"")

        def wait(self):
            self.returncode = 0
            return 0

        def kill(self):
            self.killed = True
    monkeypatch.setattr(subprocess, "Popen", Proc)
    got = []
    assert eng.stream(["docker", "pull", "nginx"], 5, got.append) == (0, "")
    assert got == ["a: Pulling fs layer", "Status: Downloaded"] and Proc.kw["stdin"] is subprocess.DEVNULL
    if os.name == "nt":
        assert Proc.kw["creationflags"] == 0x08000000  # CREATE_NO_WINDOW

    class Hung(Proc):
        def __init__(self, args, **kw):
            super().__init__(args, **kw)
            Hung.me = self
            self.stdout = self

        def readline(self):
            import time as _time
            _time.sleep(0.05)
            return b"" if self.killed else b"waiting\n"
    monkeypatch.setattr(subprocess, "Popen", Hung)
    with pytest.raises(Exception, match="took more than 0.2 s"):
        eng.stream(["docker", "pull", "big"], 0.2, lambda s: None)
    assert Hung.me.killed
