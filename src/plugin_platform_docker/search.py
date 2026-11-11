"""Find an image for anything (0.2.0; the user, 2026-11-10: "lets roll in a way to import docker images (from various docker
repos) with a search that can find things like nginx webserver or postfix secure file server w/ all the anti-spam+++";
"there needs to be enough docker description in order to understand what is being provided"; "i want to be able to get
a docker image for anything").

A search's words are read (query.py); the sources are asked at once, each within its budget of terms and the search
within DEADLINE_S (sources.py: Docker Hub through the engine, Quay, Artifact Hub; Docker Hub's website search only when
its setting is on); the curated picks its words ask for join them (catalog.py); everything is merged by reference (a
pick's other references are the pick); Docker Hub's best are enriched with what its documented API says (pulls, when
updated, categories, whether it holds a tag at all: a repository with none is no image, the way spam repositories look);
then ranked: what the search asks for first (COVERAGE), then trust, popularity, freshness and a pick of the role asked,
less what speaks against it (deprecated, a relay where a whole mail server is asked, a login needed). Each result keeps
its reasons in words. `details` says what one image is and holds: what it provides, its README's first lines (the
publisher's words, as plain text), its newest tags with their dates, sizes and platforms."""
from __future__ import annotations

import concurrent.futures
import math
import re
import time
from dataclasses import dataclass, field, replace

from .catalog import CONCEPTS, PICKS, ROLE_WORDS, kind_of
from .query import TITLES, WEAK, Query, artifacthub_query, hub_terms, normal, parse, picks_for, quay_terms
from .sources import (SOURCES, Busy, Found, Http, SourceError, artifacthub_detail, artifacthub_search, canonical, enrich_from_hub,
                      hub_allowance, hub_by_engine, hub_has_tag, hub_repository, hub_tags, hub_website, oci_tags, plain, pull_ref,
                      quay_search, quay_tags, registry_of, shown, tag_to_offer)

WEIGHTS = {"coverage": 0.40, "trust": 0.25, "popularity": 0.15, "fresh": 0.10, "pick": 0.10}
RESULTS = 25  # results shown at most
ENRICH = 8  # Docker Hub results enriched with its repository API (and checked for a tag)
DEADLINE_S = 25.0  # a search's sources answer within this, or are said as not answering
ALLOWANCE_S = 120.0  # Docker Hub's pull allowance read again after this
WHERE = ("all", "docker-hub", "quay", "artifact-hub", "catalog")
DAY = 86400.0
MISFIT = {  # a role asked, and what in a result's words says it is something else
    "mailserver": (re.compile(r"\b(relay|relayhost|smarthost|catch|catcher|mailhog|mailpit|mailcatcher|smtp sink|fake smtp|"
                              r"exporter|sendmail only|outbound only|send only)\b"),
                   "a relay or a test catcher, not a whole mail server"),
    "webserver": (re.compile(r"\b(ingress controller|ingress|exporter|operator|helm chart|kubernetes controller)\b"),
                  "made for Kubernetes or monitoring, not a server to run"),
    "proxy": (re.compile(r"\b(exporter|operator|helm chart)\b"), "made for Kubernetes or monitoring, not a proxy to run"),
}
STALE = re.compile(r"\b(deprecated|unmaintained|no longer maintained|not maintained|obsolete|archived|abandoned|end of life|eol)\b")


@dataclass(frozen=True)
class Ranked:
    """A result: the image as found, its score, its reasons in words, what of the search it covers."""

    found: Found
    score: float
    reasons: tuple[str, ...]
    covers: tuple[str, ...]


@dataclass
class Outcome:
    """A search done: its words as read, its results ranked, each source as asked ({terms, found, error}), what to say
    beside them, when (the wall's), Docker Hub's pull allowance ({limit, left, hours} or None), the engine Docker Hub was
    searched through ("" when none answered)."""

    query: Query
    where: str
    results: list[Ranked]
    asked: dict
    notes: list[str] = field(default_factory=list)
    at: float = 0.0
    allowance: dict | None = None
    engine: str = ""

    def result(self, ref: str) -> Ranked | None:
        c = canonical(ref)
        return next((r for r in self.results if r.found.ref == c), None)

    def sources(self) -> list[tuple[str, dict]]:
        """Each source as asked, always in one order (they answer in any)."""
        order = list(SOURCES)
        return sorted(self.asked.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order))


# -- merging ------------------------------------------------------------------------------------------------------------
def from_pick(p) -> Found:
    return Found(ref=p.ref, name=p.name, provides=p.provides, tag=p.tag, licence=p.licence, note=p.note, stack=p.stack,
                 official=p.trust == "official", verified=p.trust == "verified", open_source=p.trust == "open source",
                 publisher={"official": "Docker Official Images"}.get(p.trust, ""), sources=("catalog",), pick=p,
                 page=p.stack or "")


def combine(a: Found, b: Found) -> Found:
    """Two finds of one image as one: the flags of either, the higher counts, the newer date, every source; a pick's name,
    tag and words before a registry's."""
    pick = a.pick or b.pick
    first = lambda x, y: x or y  # noqa: E731
    return replace(
        a, name=(b.name if b.pick and not a.pick else first(a.name, b.name)), description=first(a.description, b.description),
        publisher=first(a.publisher, b.publisher), official=a.official or b.official, verified=a.verified or b.verified,
        open_source=a.open_source or b.open_source, signed=a.signed or b.signed,
        stars=max((x for x in (a.stars, b.stars) if x is not None), default=None),
        pulls=max((x for x in (a.pulls, b.pulls) if x is not None), default=None),
        popularity=max((x for x in (a.popularity, b.popularity) if x is not None), default=None),
        updated=max((x for x in (a.updated, b.updated) if x is not None), default=None),
        tag=(pick.tag if pick else first(a.tag, b.tag)), categories=tuple(dict.fromkeys(a.categories + b.categories)),
        keywords=tuple(dict.fromkeys(a.keywords + b.keywords)), archived=a.archived or b.archived,
        deprecated=a.deprecated or b.deprecated, needs_login=first(a.needs_login, b.needs_login), stack=first(a.stack, b.stack),
        provides=first(a.provides, b.provides), licence=first(a.licence, b.licence),
        note="; ".join(dict.fromkeys(x for x in (a.note, b.note) if x)), scan=first(a.scan, b.scan),
        page=first(a.page, b.page), sources=tuple(dict.fromkeys(a.sources + b.sources)),
        terms=tuple(dict.fromkeys(a.terms + b.terms)), pick=pick, extra={**b.extra, **a.extra})


def merge(finds) -> dict[str, Found]:
    """Every find by its reference, a pick's other references (mirrors, old names) counted as the pick when the pick is
    among them (a search of Quay alone keeps Quay's reference: it is what was asked)."""
    finds = list(finds)
    present = {f.pick.ref for f in finds if f.pick is not None}
    alias = {canonical(a): p.ref for p in PICKS if p.ref in present for a in p.aliases}
    out: dict[str, Found] = {}
    for f in finds:
        key = alias.get(f.ref, f.ref)
        f = replace(f, ref=key) if key != f.ref else f
        out[key] = combine(out[key], f) if key in out else f
    return out


# -- ranking ------------------------------------------------------------------------------------------------------------
def _present(phrase: str, text: str) -> bool:
    """A phrase in a text as a whole word (or the words together: "mail server", "mailserver")."""
    for p in {phrase, phrase.replace(" ", "")}:
        if p and re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", text):
            return True
    return False


def text_of(f: Found, provides: bool = True) -> str:
    return " " + normal(" ".join([shown(f.ref), f.name, f.description, f.provides if provides else "", " ".join(f.categories),
                                  " ".join(f.keywords)])) + " "


def coverage(q: Query, f: Found) -> tuple[float, list[str], bool]:
    """How much of the search a result covers (0..1), what in words, and whether any concept the search named (a role, a
    product, a feature; a role a product implies) is among it: a product named counts most, then a role, then a feature (a
    pick's own concepts count as said: its words are not read for them, "not Postfix" covering no Postfix); the other words
    by their presence (a weak one little); a word in its name more."""
    text, name = text_of(f, provides=f.pick is None), " " + normal(f"{shown(f.ref)} {f.name}") + " "
    own = set(getattr(f.pick, "concepts", ()) or ())
    total = got = 0.0
    covered: list[str] = []
    hit = False
    for c in q.concepts:
        kind = kind_of(c)
        if kind == "quality":
            continue
        w = {"product": 1.0, "role": 0.8, "feature": 0.6}.get(kind, 0.5)
        total += w
        words = [normal(x) for x in CONCEPTS[c][1]]
        if c in own or any(_present(x, text) for x in words):
            got += w
            hit = True
            covered.append(TITLES.get(c, c))
            if any(_present(x, name) for x in words):
                got += 0.15 * w
    for word in q.words:
        w = 0.2 if word in WEAK else 0.5
        total += w
        if _present(word, text) or (len(word) > 3 and word in text):
            got += w
            covered.append(word)
            if _present(word, name):
                got += 0.15 * w
    for r in q.roles:  # a role only implied (by a product, a feature): asked too
        if r not in q.concepts:
            total += 0.4
            if r in own or any(_present(normal(x), text) for x in CONCEPTS[r][1]):
                got += 0.4
                hit = True
    return (min(1.0, got / total) if total else 0.0), covered, hit


def trust(f: Found) -> tuple[float, str]:
    pick = f.pick
    level = getattr(pick, "trust", "")
    if f.official or level == "official":
        t, said = 1.0, "Docker Official Image" if f.ref.startswith("docker.io/library/") else "official"
    elif f.verified or level == "verified":
        t, said = 0.85, "verified publisher"
    elif f.open_source or level == "open source":
        t, said = 0.75, "sponsored open source" if f.ref.startswith("docker.io/") else "open source"
    elif level == "project":
        t, said = 0.7, "the project's own"
    else:
        t, said = 0.3, "community"
    if f.signed:
        t, said = min(1.0, t + 0.1), said + ", signed (cosign)"
    return t, said


def popularity(f: Found) -> tuple[float, str]:
    if f.pulls:
        return min(1.0, math.log10(f.pulls + 1) / 10.0), f"{_count(f.pulls)} pulls"
    if f.stars:
        return min(1.0, math.log10(f.stars + 1) / 4.5), f"{_count(f.stars)} stars"
    if f.popularity:
        return min(1.0, math.log10(f.popularity + 1) / 3.0), "busy on Quay this week"
    return (0.3, "") if f.pick else (0.0, "")


def freshness(f: Found, now: float) -> tuple[float, str]:
    if not f.updated:
        return 0.5, ""
    days = max(0.0, (now - f.updated) / DAY)
    score = 1.0 if days <= 60 else 0.85 if days <= 180 else 0.65 if days <= 365 else 0.35 if days <= 730 else 0.1
    return score, f"updated {_ago(days)}"


def rank(q: Query, f: Found, now: float) -> Ranked:
    cov, covered, hit = coverage(q, f)
    t, trust_said = trust(f)
    pop, pop_said = popularity(f)
    fresh, fresh_said = freshness(f, now)
    pick = f.pick
    picked = bool(pick) and bool(set(pick.roles) & set(q.roles) or set(pick.concepts) & set(q.of("product")))
    score = (WEIGHTS["coverage"] * cov + WEIGHTS["trust"] * t + WEIGHTS["popularity"] * pop + WEIGHTS["fresh"] * fresh
             + WEIGHTS["pick"] * (1.0 if picked else 0.0))
    reasons = [trust_said]
    said_covered = [x for x in dict.fromkeys(covered) if x not in WEAK]  # "server" counts a little, says nothing
    if said_covered:
        reasons.append("covers " + ", ".join(said_covered))
    if picked:
        role = next((r for r in pick.roles if r in q.roles), "")
        reasons.append(f"Liminal's pick for {ROLE_WORDS[role]}" if role else "Liminal's pick")
    reasons += [x for x in (pop_said, fresh_said, f.scan) if x]
    text = text_of(f)
    named = any(kind_of(c) != "quality" for c in q.concepts)  # the search names what it is for
    if q.secure and (hit or not named) and (f.official or f.verified or f.signed or "secure" in getattr(pick, "concepts", ()) or
                                            _present("rootless", text) or _present("unprivileged", text) or _present("hardened", text)):
        score += 0.05
    if pick is not None and pick.penalty:
        score -= pick.penalty
    if named and not hit:  # none of what the search is for: below anything that is (a relay where a mail server is asked too)
        score -= 0.4
        reasons.append("matches only the search's other words" + (f" ({', '.join(covered)})" if covered else ""))
    if f.archived or f.deprecated:
        score -= 0.35
        reasons.append("archived or deprecated")
    elif STALE.search(text):
        score -= 0.25
        reasons.append("its own words say it is no longer kept up")
    for r in q.roles:
        misfit = MISFIT.get(r)
        if misfit and misfit[0].search(text) and not (r == "mailserver" and (_present("imap", text) or _present("dovecot", text))):
            score -= 0.25
            reasons.append(misfit[1])
            break
    if f.needs_login:
        score -= 0.1
        reasons.append("needs a sign-in to pull")
    if f.stack:
        reasons.append("a compose stack of several images: installed its own way, not one pull")
    if f.note:
        reasons.append(f.note)
    return Ranked(f, round(score, 4), tuple(dict.fromkeys(reasons)), tuple(dict.fromkeys(covered)))


def _count(n: int) -> str:
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            v = n / size
            return (f"{v:.1f}".removesuffix(".0") if v < 100 else f"{v:.0f}") + unit  # 12.7M, 13.6B, 150K
    return f"{n:,}"


def _ago(days: float) -> str:
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 60:
        return f"{int(days)} days ago"
    if days < 730:
        return f"{int(days / 30.4)} months ago"
    return f"{days / 365.25:.0f} years ago"


# -- the search ---------------------------------------------------------------------------------------------------------
class Searcher:
    """The searches and the details, over one Http (its turns and cache shared); `wall` the clock for "updated"."""

    def __init__(self, http: Http | None = None, wall=None):
        self.http = http or Http()
        self._wall = wall or time.time
        self._allowance: tuple[float, dict | None] | None = None

    def allowance(self) -> dict | None:
        """Docker Hub's anonymous pulls left from here, read at most every ALLOWANCE_S."""
        now = time.monotonic()
        if self._allowance is not None and now - self._allowance[0] < ALLOWANCE_S:
            return self._allowance[1]
        try:
            got = hub_allowance(self.http)
        except Exception:  # noqa: BLE001 - the allowance unread is said as nothing; the search stands
            got = None
        self._allowance = (now, got)
        return got

    def search(self, text: str, where: str = "all", engine=None, engine_name: str = "", website: bool = False) -> Outcome:
        q = parse(text)
        if q.empty:
            raise ValueError("nothing to search for: say what the image is for (nginx web server, postfix mail server with "
                             "anti-spam, postgres, home assistant ...)")
        where = where if where in WHERE else "all"
        want = lambda s: where in ("all", s)  # noqa: E731
        asked: dict[str, dict] = {}
        work: dict[str, tuple[list[str], object]] = {}
        if want("docker-hub"):
            terms = hub_terms(q)
            if engine is not None:
                work["docker-hub"] = (terms, lambda t: hub_by_engine(engine, t))
            else:
                asked["docker-hub"] = {"terms": terms, "found": 0, "error": "not searched: no Docker engine answers (Docker Hub is "
                                       "searched through a running engine; start Liminal-Ubuntu from its WSL plugin)"}
            if website:
                work["hub-website"] = (terms[:2], lambda t: hub_website(self.http, t))
        if want("quay"):
            work["quay"] = (quay_terms(q), lambda t: quay_search(self.http, t))
        if want("artifact-hub"):
            ah = artifacthub_query(q)
            if ah:
                work["artifact-hub"] = ([ah], lambda t: artifacthub_search(self.http, t))
        finds: list[Found] = []
        if work:
            # not `with`: its exit would wait for a late source too. Each source stops at the deadline between its terms
            # (no request or command after the search answered, but the one under way ends on its own timeout); what its
            # terms found before it is kept.
            deadline = time.monotonic() + DEADLINE_S
            sinks: dict[str, list] = {name: [] for name in work}
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(work), thread_name_prefix="image-search")
            try:
                futures = {pool.submit(self._ask, name, terms, fn, deadline, sinks[name]): name for name, (terms, fn) in work.items()}
                done, late = concurrent.futures.wait(futures, timeout=max(0.0, deadline - time.monotonic()))
                for fut in done:
                    name = futures[fut]
                    got, error = fut.result()
                    asked[name] = {"terms": work[name][0], "found": len(got), "error": error}
                for fut in late:
                    name = futures[fut]
                    asked[name] = {"terms": work[name][0], "found": len(list(sinks[name])),
                                   "error": f"not every term answered within {DEADLINE_S:g} s"}
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            order = list(SOURCES)
            for name in sorted(work, key=lambda n: order.index(n) if n in order else len(order)):  # one order: one merge
                finds += list(sinks[name])
        if want("catalog"):
            picks = picks_for(q, PICKS)
            finds = [from_pick(p) for p in picks] + finds  # a pick's words first
            asked["catalog"] = {"terms": [], "found": len(picks), "error": ""}
        merged = merge(finds)
        now = self._wall()
        notes: list[str] = []
        self._enrich(q, merged, now, notes)
        ranked = sorted((rank(q, f, now) for f in merged.values() if f.tag_count != 0),
                        key=lambda r: (-r.score, -(r.found.pulls or 0), r.found.ref))
        gone = sum(1 for f in merged.values() if f.tag_count == 0)
        if gone:
            notes.append(f"{gone} Docker Hub repositor{'y' if gone == 1 else 'ies'} left out: no image in {'it' if gone == 1 else 'them'} (no tag)")
        results = ranked[:RESULTS]
        allowance = self.allowance() if any(r.found.ref.startswith("docker.io/") and not r.found.stack for r in results) else None
        return Outcome(q, where, results, asked, notes, now, allowance, engine_name if engine is not None else "")

    def _ask(self, name: str, terms: list[str], fn, deadline: float, sink: list) -> tuple[list[Found], str]:
        """One source's terms in turn until the deadline, each one's finds put in `sink` as they come: what they found,
        and the first error ("" for none; a host asking to wait ends it)."""
        error = ""
        for t in terms:
            if time.monotonic() >= deadline:
                return list(sink), f"not every term answered within {DEADLINE_S:g} s"
            try:
                sink.extend(fn(t))
            except Busy as e:
                return list(sink), str(e)
            except SourceError as e:
                error = error or str(e)
            except Exception as e:  # noqa: BLE001 - an engine's refusal, an unexpected answer: said, the search goes on
                error = error or (f"{type(e).__name__}: {e}".splitlines()[0])[:200]
        return list(sink), ("" if sink else error)

    def _enrich(self, q: Query, merged: dict, now: float, notes: list[str]) -> None:
        """Docker Hub's most likely results given what its documented API says (pulls, when updated, categories) and
        whether they hold a tag at all, ENRICH at most, in turn. The tag offered: a pick's advice; else 'latest' when the
        repository holds it (asked by name: a page of tags is only the newest); else, from the newest page, the newest
        that is an image and no development build (never a signature or an attestation)."""
        hub = [f for f in merged.values() if f.ref.startswith("docker.io/") and not f.stack]
        hub.sort(key=lambda f: -rank(q, f, now).score)
        for f in hub[:ENRICH]:
            try:
                enrich_from_hub(f, hub_repository(self.http, f.ref))
                count, tags = hub_tags(self.http, f.ref, 10)
                f.tag_count = count if count is not None else len(tags)
                names = [t["name"] for t in tags]
                whole = count is not None and count <= len(names)  # the page is every tag it has
                if f.pick is None and f.tag and f.tag not in names and (whole or not hub_has_tag(self.http, f.ref, f.tag)):
                    f.tag = ""  # a version another source named, not there
                if f.pick is None and not f.tag and names:
                    f.tag = "latest" if "latest" in names or (not whole and hub_has_tag(self.http, f.ref, "latest")) else tag_to_offer(names)
            except Busy as e:
                notes.append(f"Docker Hub's details not read: {e}")
                return
            except SourceError as e:
                if "not found" in str(e) and f.tag_count is None:
                    f.tag_count = 0  # no such repository
            except Exception:  # noqa: BLE001 - one image's details unread: the search stands
                continue

    # -- details -----------------------------------------------------------------------------------------------------
    def details(self, ref: str, outcome: Outcome | None = None) -> tuple[str, list[str]]:
        """What one image is and holds, in words: (a heading, lines). Its registry and publisher, trust, what it
        provides, its description and README's first lines (the publisher's words, as plain text), its newest tags."""
        c = canonical(ref)
        if not c:
            raise ValueError(f"not an image's name: {ref!r}")
        known = outcome.result(c) if outcome is not None else None
        f = known.found if known else next((from_pick(p) for p in PICKS if p.ref == c), Found(ref=c, name=shown(c)))
        lines: list[str] = []
        lines.append(f"Where: {registry_of(c)} · {shown(c)}" + (f" · by {f.publisher}" if f.publisher else ""))
        if known:
            lines.append("Why it ranks here: " + "; ".join(known.reasons))
        if f.provides:
            lines.append("What it provides: " + f.provides)
        if f.description and f.description != f.provides:
            lines.append("Its own description: " + f.description)
        if f.categories:
            lines.append("Categories: " + ", ".join(f.categories))
        if f.licence:
            lines.append("Licence: " + f.licence)
        if f.stack:
            lines.append(f"Installed as a compose stack, not one pull: {f.stack}")
        if f.needs_login:
            lines.append("Needs a sign-in: " + f.needs_login)
        readme: list[str] = []
        tags: list[str] = []
        tags_said = "Newest tags:"
        problems: list[str] = []
        try:  # each part read on its own: one that fails leaves the others
            if c.startswith("docker.io/") and not f.stack:
                repo = hub_repository(self.http, c)
                enrich_from_hub(f, repo)
                readme = plain(f.extra.get("full_description", ""))
                count, got = hub_tags(self.http, c, 10)
                tags = [_tag_line(t, self._wall()) for t in got]
                if count is not None:
                    lines.append(f"Tags: {count:,} in all" + (f" · {_count(f.pulls)} pulls" if f.pulls else "")
                                 + (f" · {f.stars:,} stars" if f.stars is not None else ""))
            elif c.startswith("quay.io/"):
                tags = [_tag_line(t, self._wall()) for t in quay_tags(self.http, c, 10)]
            elif not f.stack:
                names = oci_tags(self.http, c, 100)
                tags = [", ".join(names[:15]) + (f" … ({len(names)} listed)" if len(names) > 15 else "")] if names else []
                tags_said = "Tags (as its registry lists them, not by date):"
        except SourceError as e:
            problems.append(str(e))
        except Exception as e:  # noqa: BLE001 - an answer in a shape not foreseen: said, the rest read
            problems.append(f"{type(e).__name__}: {e}"[:200])
        try:
            if "ah" in f.extra and all(f.extra["ah"]):
                d = artifacthub_detail(self.http, *f.extra["ah"])
                readme = readme or plain(str(d.get("readme") or ""))
                plats = (d.get("data") or {}).get("platforms") or [] if isinstance(d.get("data"), dict) else []
                if plats:
                    lines.append("Platforms: " + ", ".join(str(p) for p in plats[:8]))
                links = [f"{x.get('name')}: {x.get('url')}" for x in d.get("links") or [] if isinstance(x, dict) and x.get("url")]
                if links:
                    lines.append("Links: " + " · ".join(links[:4]))
        except SourceError as e:
            problems.append(str(e))
        except Exception as e:  # noqa: BLE001
            problems.append(f"{type(e).__name__}: {e}"[:200])
        if tags:
            lines.append(tags_said)
            lines += ["  " + t for t in tags]
        if readme:
            lines.append("Its README (the publisher's words, first lines):")
            lines += ["  " + x for x in readme]
        lines += [f"Not read: {p}" for p in problems]
        if not f.stack:
            lines.append(f"Pulled as: {pull_ref(c, f.tag)}")
        return f"Details of {f.name or shown(c)} ({registry_of(c)})", lines  # its name as written: lower case kept


def _tag_line(t: dict, now: float) -> str:
    parts = [t["name"]]
    if t.get("updated"):
        parts.append(_ago(max(0.0, (now - t["updated"]) / DAY)))
    if t.get("size"):
        parts.append(f"{t['size'] / 1e6:,.0f} MB")
    if t.get("platforms"):
        parts.append(", ".join(t["platforms"][:6]) + (" …" if len(t["platforms"]) > 6 else ""))
    if t.get("active") is False:
        parts.append("inactive")
    return " · ".join(parts)


def where_choices() -> list[dict]:
    return [{"value": "all", "title": "Everywhere", "note": "every source on (Docker Hub through a running engine)"},
            {"value": "docker-hub", "title": SOURCES["docker-hub"], "note": "through a running Docker engine"},
            {"value": "quay", "title": SOURCES["quay"], "note": "Red Hat's registry: many projects' own images"},
            {"value": "artifact-hub", "title": SOURCES["artifact-hub"], "note": "an index of images on many registries: signatures, scans"},
            {"value": "catalog", "title": SOURCES["catalog"], "note": "known web servers, reverse proxies and mail servers"}]
