"""A search's words read (0.2.0): the roles, products, features and qualities the concept table knows (catalog.CONCEPTS),
the user's other words kept as they are (a search is for anything: "home assistant", "postgres", "minio" go by their own
words), and the few terms each registry is asked for, within its budget. Nothing here asks anyone."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import CONCEPTS, ROLE_WORDS, kind_of

# words that say nothing about what is wanted in an image search
FILLER = frozenset({
    "a", "an", "the", "w", "with", "all", "and", "or", "plus", "for", "of", "my", "some", "to", "in", "on", "that", "which",
    "please", "want", "need", "needs", "image", "images", "docker", "dockerized", "dockerised", "container", "containers",
    "something", "thing", "get", "find", "me", "i", "is", "it", "be", "good", "best", "new", "up", "set", "run", "running",
    "one", "any", "anything", "like", "etc", "also", "using", "use", "includes", "including", "full", "complete",
})
WEAK = frozenset({"server", "service", "app", "tool", "official"})  # kept, but they say little
IMPLIES = {  # a product or a feature asks for its role (ClamAV, Let's Encrypt, fail2ban serve far more than mail: none)
    "nginx": "webserver", "apache": "webserver", "caddy": "webserver", "openresty": "webserver",
    "traefik": "proxy", "haproxy": "proxy",
    "postfix": "mailserver", "dovecot": "mailserver", "exim": "mailserver", "haraka": "mailserver",
    "stalwart": "mailserver", "maddy": "mailserver", "mox": "mailserver",
    "antispam": "mailserver", "mailauth": "mailserver", "imap": "mailserver", "smtp": "mailserver", "webmail": "mailserver",
}
# a concept's words that name a project of their own: also kept as the user's word, so its own image is asked for by its
# name ("rspamd" searches rspamd, not only "antispam")
SPECIFIC = frozenset({"rspamd", "spamassassin", "postgrey", "postscreen", "clamav", "opendkim", "opendmarc", "certbot",
                      "fail2ban", "crowdsec", "roundcube", "sogo", "snappymail", "httpd"})
ROLE_TERMS = {"webserver": "webserver", "proxy": "reverse proxy", "mailserver": "mailserver"}  # Docker Hub's best word for each
QUAY_ROLE = {"webserver": "webserver", "proxy": "proxy", "mailserver": "mailserver"}
HUB_ROLE = {"webserver": "web", "proxy": "proxy", "mailserver": "mail"}  # Artifact Hub matches words as prefixes
FEATURE_TERMS = {"antispam": "antispam", "antivirus": "clamav", "mailauth": "dkim", "webmail": "webmail", "tls": "letsencrypt",
                 "bruteforce": "fail2ban", "imap": "imap", "smtp": "smtp"}
TITLES = {  # a concept in words (the reading said back)
    "webserver": "a web server", "proxy": "a reverse proxy", "mailserver": "a mail server", "nginx": "nginx",
    "apache": "Apache httpd", "caddy": "Caddy", "traefik": "Traefik", "haproxy": "HAProxy", "openresty": "OpenResty",
    "postfix": "Postfix", "dovecot": "Dovecot", "exim": "Exim", "haraka": "Haraka", "stalwart": "Stalwart",
    "maddy": "Maddy", "mox": "mox", "antispam": "anti-spam", "antivirus": "antivirus", "mailauth": "DKIM, DMARC and SPF",
    "imap": "IMAP", "smtp": "SMTP", "tls": "TLS certificates", "bruteforce": "brute-force blocking", "webmail": "webmail",
    "secure": "secure", "rootless": "rootless",
}
MAX_CHARS = 200  # a query longer than this is cut
MAX_WORDS = 12


def normal(text: str) -> str:
    """Lower case, "w/" as "with", every mark a space ("anti-spam" is "anti spam", "node.js" is "node js"); letters of any
    language kept whole ("café", "gitea" alike)."""
    s = str(text or "").lower().replace("w/", " with ")
    return " ".join(re.sub(r"[\W_]+", " ", s).split())


def _phrases() -> dict[str, str]:
    """Each concept word as normal() reads it, and its compound without spaces, to its concept id."""
    out: dict[str, str] = {}
    for cid, (_, words) in CONCEPTS.items():
        for w in words:
            n = normal(w)
            if n:
                out.setdefault(n, cid)
                out.setdefault(n.replace(" ", ""), cid)
    return out


PHRASES = _phrases()


@dataclass(frozen=True)
class Query:
    """A search's words as read: the text typed (cut at MAX_CHARS), the concepts known in it in order, the other words
    (in order, filler dropped), and the roles asked for (named, or implied by a product or a feature)."""

    text: str
    concepts: tuple[str, ...]
    words: tuple[str, ...]
    roles: tuple[str, ...]

    @property
    def empty(self) -> bool:
        """Nothing that says what the image is for ("secure" alone says how, not what)."""
        return not self.words and all(kind_of(c) == "quality" for c in self.concepts)

    def of(self, kind: str) -> tuple[str, ...]:
        return tuple(c for c in self.concepts if kind_of(c) == kind)

    @property
    def secure(self) -> bool:
        return "secure" in self.concepts or "rootless" in self.concepts

    def said(self) -> str:
        """The reading in words: "a mail server · Postfix · anti-spam · secure; other words: file, server"."""
        parts = [ROLE_WORDS[r] for r in self.roles]
        parts += [TITLES.get(c, c) for c in self.concepts if kind_of(c) != "role"]
        out = " · ".join(dict.fromkeys(parts))
        if self.words:
            out += ("; other words: " if out else "") + ", ".join(self.words)
        return out or "nothing to search for"


def parse(text: str) -> Query:
    """The words of a search read: known phrases first (a compound before its parts: "web server", "anti spam", also
    written together), each known once; the rest kept unless filler."""
    typed = " ".join(str(text or "").split())[:MAX_CHARS]
    tokens = normal(typed).split()[: MAX_WORDS * 3]
    concepts: list[str] = []
    words: list[str] = []
    by_name: set[str] = set()  # concepts said only by a project's own name ("rspamd": that project asked for, not a mail server)
    said_plainly: set[str] = set()
    i = 0
    while i < len(tokens):
        hit = None
        for n in (3, 2, 1):
            if i + n > len(tokens):
                continue
            part = tokens[i:i + n]
            for key in (" ".join(part), "".join(part)):
                if key in PHRASES:
                    hit = (PHRASES[key], n)
                    break
            if hit:
                break
        if hit:
            if hit[0] not in concepts:
                concepts.append(hit[0])
            literal = "".join(tokens[i:i + hit[1]])
            if literal in SPECIFIC:  # a project's own name: asked for by it too
                by_name.add(hit[0])
                if literal not in words:
                    words.append(literal)
            else:
                said_plainly.add(hit[0])
            i += hit[1]
            continue
        w = tokens[i]
        if w not in FILLER and w not in words and len(w) > 1:
            words.append(w)
        i += 1
    roles = [c for c in concepts if kind_of(c) == "role"]
    for c in concepts:
        r = IMPLIES.get(c)
        if r and r not in roles and not (c in by_name and c not in said_plainly):  # "rspamd" alone asks for rspamd itself
            roles.append(r)
    return Query(typed, tuple(concepts[:MAX_WORDS]), tuple(words[:MAX_WORDS]), tuple(roles))


def _unique(items, budget: int) -> list[str]:
    out: list[str] = []
    for t in items:
        t = " ".join(str(t or "").split())
        if t and t not in out:
            out.append(t)
        if len(out) >= budget:
            break
    return out


def _strong(q: Query) -> list[str]:
    """The other words that say something, the longest first (the weak ones last)."""
    return sorted(q.words, key=lambda w: (w in WEAK, -len(w)))


def hub_terms(q: Query, budget: int = 3) -> list[str]:
    """Docker Hub's search through the engine (`docker search`: it matches names and descriptions, several words ORed):
    each product named, the user's own words together, the role's word, a feature's, then the other words alone."""
    products = list(q.of("product"))
    own = " ".join([w for w in q.words if w not in WEAK][:3]) if q.words and not products else ""  # as typed: "home assistant"
    roles = [ROLE_TERMS[r] for r in q.roles]
    features = [FEATURE_TERMS[f] for f in q.of("feature") if f in FEATURE_TERMS]
    return _unique([*products, own, *roles, *features[:1], *_strong(q)], budget)


def quay_terms(q: Query, budget: int = 3) -> list[str]:
    """Quay's search (one substring of the name or the description a call: no spaces): products, the role's word, the
    other words alone."""
    products = list(q.of("product"))
    roles = [QUAY_ROLE[r] for r in q.roles]
    features = [FEATURE_TERMS[f] for f in q.of("feature") if f in FEATURE_TERMS]
    words = [w for w in _strong(q) if w not in WEAK]
    # a role known: its features before the words the table does not know ("file" in "postfix ... file server")
    return _unique([*products, *roles, *features[:1], *words] if roles else [*products, *words, *features[:1]], budget)


def artifacthub_query(q: Query, most: int = 5) -> str:
    """Artifact Hub's one search: its words ORed ("postfix or mail or antispam"; it matches whole words as prefixes, never
    inside a word, and does not stem)."""
    products = list(q.of("product"))
    roles = [HUB_ROLE[r] for r in q.roles]
    features = [FEATURE_TERMS[f] for f in q.of("feature") if f in FEATURE_TERMS]
    words = [w for w in _strong(q) if w not in WEAK]
    terms = _unique([*products, *roles, *features, *words] if roles else [*products, *words, *features], most)
    return " or ".join(t.replace(" ", "") for t in terms)


def picks_for(q: Query, picks) -> list:
    """The curated picks a search asks for: those of a role it asks for, or named by it (a product they cover, their own
    name)."""
    out = []
    named = set(q.of("product"))
    asked = set(q.words) - WEAK
    for p in picks:
        own = set(normal(p.name).split()) - NAME_WORDS  # its own name's words: "swag", "mailcow", "poste", "iredmail"
        if set(p.roles) & set(q.roles) or set(p.concepts) & named or asked & own:
            out.append(p)
    return out


# the words of a pick's name that are no name of its own ("SWAG (Secure Web Application Gateway)", "Poste.io (free edition)")
NAME_WORDS = frozenset({"secure", "web", "application", "gateway", "server", "http", "edition", "free", "dockerized",
                        "unprivileged", "the", "of", "a", "io", "mail"})
