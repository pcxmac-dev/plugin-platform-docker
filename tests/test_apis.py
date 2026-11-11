"""What the plugin attaches to (plugin API 2.2; the user, 2026-11-11: "each plugin should reflect the the API its attached
to, and present links that provide documentation"): its cards are sound; they name every call the plugin makes (each
command its engines are given, each address the registries are asked, both read from the stand-ins as the plugin sends
them) and claim none it does not make; its facts ask nothing; and, with LIMINAL_VENDOR_PAGES=1 alone, every address on
them answers (the only test here that reaches the network)."""
from __future__ import annotations

import inspect
import os
import re
import urllib.parse

import pytest

import plugin_platform_docker as dk
from liminal_libs import docker as library_docker
from liminal_libs.sources import apis as A
from liminal_libs.sources.conformance import problems
from plugin_platform_docker import apis as cards
from test_search import HUB_SEARCH, TAGS, hub, iso, page_plugin

# the docker command's management groups (its reference's index): their commands are two words (docker volume ls)
GROUPS = {"builder", "buildx", "checkpoint", "compose", "config", "container", "context", "debug", "desktop", "dhi", "image",
          "manifest", "mcp", "model", "network", "node", "offload", "pass", "plugin", "scout", "secret", "service", "stack",
          "swarm", "system", "trust", "volume"}
MANY = {cards.OCI: {"name"}, cards.QUAY: {"repository"}}  # a placeholder that holds a slash (library/nginx, owner/name)


def verb(words) -> str:
    """A docker command by its command words: ps, volume ls, rmi."""
    words = list(words)
    return " ".join(words[:2]) if words[0] in GROUPS and len(words) > 1 else words[0]


def card(name: str) -> A.Api:
    return next(a for a in dk.MACHINE.apis if a.name == name)


def pattern(api: A.Api, call: A.Call) -> tuple[str, re.Pattern]:
    method, _, path = call.name.partition(" ")
    many = MANY.get(api.name, set())
    rx = re.sub(r"\\\{([^}]*)\\\}", lambda m: ".+" if m.group(1) in many else "[^/]+", re.escape(path.split("?", 1)[0]))
    return method, re.compile(rx + r"\Z")


def named(api: A.Api, method: str, url: str) -> A.Call | None:
    """The card's call that a request is (a token from a realm: by its scope)."""
    parts = urllib.parse.urlsplit(url)
    if api.name == cards.OCI and "scope=repository" in urllib.parse.unquote(parts.query):
        return next(c for c in api.calls if c.name.startswith("GET {realm}"))
    base = urllib.parse.urlsplit(api.base).path if api.base.startswith("https://") else ""
    path = parts.path[len(base):] if base and parts.path.startswith(base) else parts.path
    for c in api.calls:
        m, rx = pattern(api, c)
        if m == method and rx.match(path):
            return c
    return None


def flows():
    """The plugin doing everything it does, against stand-ins: the engines read, an image searched (Docker Hub's website
    search on too) and described from each registry, a container stopped, started, restarted, removed, its log read, an
    image pulled and removed. Every docker command and every request, as sent."""
    p, engine, reg = page_plugin(website="on")
    p.status()
    # a repository whose newest tags do not hold latest: the tag is asked by its name (test_search's postgres)
    TAGS["library/postgres"] = {"count": 1400, "results": [{"name": f"13.{n}-alpine3.22", "last_updated": iso(1), "images": []}
                                                          for n in range(10)]}
    HUB_SEARCH["postgres"] = [hub("postgres", "The PostgreSQL object-relational database system", 14000, official=True)]
    try:
        p.search("postgres")
    finally:
        del TAGS["library/postgres"], HUB_SEARCH["postgres"]
    p.search("postfix mail server with anti-spam")  # the results the details below are of
    for image in ("mailserver/docker-mailserver", "quay.io/panubo/postfix", "registry.opensuse.org/opensuse/postfix",
                  "lscr.io/linuxserver/swag"):
        p.details(image)
    p.container("wsl-ubuntu", "web", "stop")
    p.container("wsl-ubuntu", "web", "start")
    p.container("wsl-ubuntu", "web", "restart")
    p.logs("wsl-ubuntu", "web", 20)
    p.remove_container("wsl-ubuntu", "web", True)
    p.pull("wsl-ubuntu", "nginx:1.27")
    p.remove_image("wsl-ubuntu", "nginx:1.27", True)
    return p, engine, reg


def test_its_cards_are_sound_and_written_for_plugin_api_2_2():
    p = dk.MACHINE
    assert p.api == "2.2" and problems(p) == [] and A.problems(p.apis) == []
    assert [a.name for a in p.apis] == [cards.CLI, cards.HUB, cards.QUAY, cards.ARTIFACTHUB, cards.OCI]
    for a in p.apis:
        assert a.verified == "2026-11-11" and a.docs.startswith("https://") and a.used and a.covered
        assert all(c.area in {x.name for x in a.areas} for c in a.calls), a.name  # every call in one of its parts
        assert len(a.areas) > len(a.covered) and len(a.calls) > len(a.used)  # more of the API than the plugin uses
    assert p.interface()["apis"] == [a.name for a in p.apis]


def test_the_cards_name_every_call_the_plugin_makes_and_no_other():
    p, engine, reg = flows()
    made = {verb(a) for a in engine.asked}
    # `docker context ls` is the library's (docker.instances, on this machine's docker alone: none on a test's PATH)
    assert '"context", "ls"' in inspect.getsource(library_docker.instances)
    made.add("context ls")
    cli = card(cards.CLI)
    claimed = {verb(c.name.split()[1:]) for c in cli.used}
    assert made == claimed, (made ^ claimed)
    assert all(c.name.split()[0] == "docker" for c in cli.calls)
    asked: dict[str, set[str]] = {}
    for method, url, _ in reg.asked:
        host = urllib.parse.urlsplit(url).hostname
        api = card(cards.HOSTS.get(host, cards.OCI))
        c = named(api, method, url)
        assert c is not None and c.used, f"{method} {url}: not on the {api.name} card as a call it makes"
        asked.setdefault(api.name, set()).add(c.name)
    for name in (cards.HUB, cards.QUAY, cards.ARTIFACTHUB, cards.OCI):
        assert asked.get(name) == {c.name for c in card(name).used}, name  # each call it says it makes, made
    hosts = {urllib.parse.urlsplit(u).hostname for _, u, _ in reg.asked}
    assert {"hub.docker.com", "quay.io", "artifacthub.io", "auth.docker.io", "registry-1.docker.io", "ghcr.io"} <= hosts


def test_the_changes_are_marked_as_writes_and_none_costs():
    cli = card(cards.CLI)
    writes = {verb(c.name.split()[1:]) for c in cli.used if c.writes}
    assert writes == {"start", "stop", "restart", "rm", "pull", "rmi"}
    assert not any(c.costs for a in dk.MACHINE.apis for c in a.calls)
    assert not any(c.writes for a in dk.MACHINE.apis if a.name != cards.CLI for c in a.used)  # the registries: read only


def test_its_facts_say_what_it_learned_and_ask_nothing():
    assert dk.DockerPlugin().api_facts() == {}  # nothing read yet, nothing asked
    p, engine, reg = flows()
    p.status()  # the platform's page reads again after a change
    before = (len(engine.asked), len(reg.asked))
    facts = A.facts_of(p)
    assert (len(engine.asked), len(reg.asked)) == before  # asked nothing to answer
    assert set(facts) == {cards.CLI, cards.HUB, cards.QUAY, cards.ARTIFACTHUB, cards.OCI}
    assert facts[cards.CLI]["Engine"].startswith("wsl-ubuntu ") and facts[cards.CLI]["Engines"] == "1 answering of 1"
    assert facts[cards.HUB]["Anonymous pulls left"].startswith("97 of 100 per 1 h from this network")
    assert facts[cards.QUAY]["Requests to quay.io"].endswith(" made")
    assert {k for k in facts[cards.OCI]} >= {"Requests to auth.docker.io", "Requests to ghcr.io"}


@pytest.mark.skipif(os.environ.get("LIMINAL_VENDOR_PAGES") != "1", reason="reaches the makers' pages: LIMINAL_VENDOR_PAGES=1")
def test_every_address_on_its_cards_answers(monkeypatch):
    monkeypatch.undo()  # this test alone reaches the network (conftest refuses it to every other)
    assert A.dead_links(dk.MACHINE.apis) == []
