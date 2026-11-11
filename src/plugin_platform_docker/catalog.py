"""What the image search knows before it asks anyone (0.2.0; the user, 2026-11-10: "lets roll in a way to import docker
images (from various docker repos) with a search that can find things like nginx webserver or postfix secure file server
w/ all the anti-spam+++"; "there needs to be enough docker description in order to understand what is being provided";
"i want to be able to get a docker image for anything").

- CONCEPTS: the words a query may use for a role (web server, reverse proxy, mail server), a product, a feature or a
  quality, so "postfix secure file server w/ all the anti-spam" is read as a mail server built on Postfix with anti-spam,
  wanted secure. A search for anything else goes by its own words: the table only helps read and rank.
- PICKS: a few images for the roles the user named, each with what it provides in words, its references, whether one
  image runs it or a compose stack of many (a stack is listed, not pulled), the tag suggested, its licence and status.
  They join a search's results when its words ask for their role or name them, ranked with the rest (never in place of
  what the registries answer). Facts checked against each project's own pages and registries on CHECKED; tags and
  digests are always read live (Details), never trusted from here.
"""
from __future__ import annotations

from dataclasses import dataclass

CHECKED = "2026-11-11"

# concept id -> (kind, words). Kinds: role, product, feature, quality. A word may be two (a compound: "web server").
CONCEPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    # roles
    "webserver": ("role", ("web server", "webserver", "web", "http server", "website", "static site", "web site")),
    "proxy": ("role", ("reverse proxy", "proxy", "load balancer", "loadbalancer", "ingress", "edge router", "gateway")),
    "mailserver": ("role", ("mail server", "mailserver", "mail", "email", "e-mail", "smtp server", "mta", "mx")),
    # products
    "nginx": ("product", ("nginx",)),
    "apache": ("product", ("apache", "httpd")),
    "caddy": ("product", ("caddy",)),
    "traefik": ("product", ("traefik",)),
    "haproxy": ("product", ("haproxy",)),
    "openresty": ("product", ("openresty",)),
    "postfix": ("product", ("postfix",)),
    "dovecot": ("product", ("dovecot",)),
    "exim": ("product", ("exim",)),
    "haraka": ("product", ("haraka",)),
    "stalwart": ("product", ("stalwart",)),
    "maddy": ("product", ("maddy",)),
    "mox": ("product", ("mox",)),
    # features
    "antispam": ("feature", ("anti-spam", "antispam", "anti spam", "spam", "rspamd", "spamassassin", "greylisting",
                             "postgrey", "postscreen", "dnsbl")),
    "antivirus": ("feature", ("antivirus", "anti-virus", "virus", "clamav")),
    "mailauth": ("feature", ("dkim", "dmarc", "spf", "arc", "opendkim", "opendmarc")),
    "imap": ("feature", ("imap", "pop3", "sieve")),
    "smtp": ("feature", ("smtp", "submission")),
    "tls": ("feature", ("tls", "ssl", "https", "letsencrypt", "let's encrypt", "acme", "certbot", "certificates")),
    "bruteforce": ("feature", ("fail2ban", "crowdsec", "brute force", "bruteforce", "ip blocking")),
    "webmail": ("feature", ("webmail", "roundcube", "sogo", "snappymail")),
    # qualities
    "secure": ("quality", ("secure", "security", "hardened", "safe")),
    "rootless": ("quality", ("rootless", "unprivileged", "non-root", "nonroot")),
}

ROLE_WORDS = {"webserver": "a web server", "proxy": "a reverse proxy", "mailserver": "a mail server"}


@dataclass(frozen=True)
class Pick:
    """One image (or compose stack) the search knows for a role: `ref` its canonical reference without a tag (a stack:
    its project's address), `provides` what it provides in words, `concepts` the concept ids it covers, `tag` the tag
    suggested (its project's own advice), `aliases` the same image elsewhere, `stack` the install page of a compose
    project of several images (listed, never pulled as one), `trust` official | verified | open source | project |
    community, `note` a caveat said beside it, `penalty` for what should keep it low (abandoned)."""

    name: str
    ref: str
    roles: tuple[str, ...]
    provides: str
    concepts: tuple[str, ...]
    tag: str = "latest"
    aliases: tuple[str, ...] = ()
    stack: str = ""
    licence: str = ""
    trust: str = "community"
    note: str = ""
    penalty: float = 0.0


PICKS: tuple[Pick, ...] = (
    # -- web servers and reverse proxies ---------------------------------------------------------------------------
    Pick("nginx", "docker.io/library/nginx", ("webserver", "proxy"),
         "nginx: web server, reverse proxy, load balancer and TCP/UDP stream proxy, HTTP/2 and HTTP/3, TLS with "
         "certificates you supply (no ACME client of its own)",
         ("nginx", "webserver", "proxy", "tls"), tag="stable", licence="BSD-2-Clause", trust="official",
         aliases=("public.ecr.aws/docker/library/nginx",)),
    Pick("nginx, unprivileged", "docker.io/nginx/nginx-unprivileged", ("webserver", "proxy"),
         "the official nginx build run as an unprivileged user (it listens on 8080, not 80); rebuilt weekly and on "
         "every nginx release or critical CVE",
         ("nginx", "webserver", "proxy", "rootless", "secure"), tag="stable", licence="Apache-2.0 (images), BSD-2-Clause (nginx)",
         trust="verified", aliases=("ghcr.io/nginx/nginx-unprivileged", "quay.io/nginx/nginx-unprivileged",
                                    "docker.io/nginxinc/nginx-unprivileged")),
    Pick("Caddy", "docker.io/library/caddy", ("webserver", "proxy"),
         "Caddy 2: web server and reverse proxy with automatic HTTPS (its own ACME client: Let's Encrypt and ZeroSSL), "
         "on-demand TLS and HTTP/3; plugins need a custom build from its -builder image",
         ("caddy", "webserver", "proxy", "tls", "secure"), tag="2", licence="Apache-2.0", trust="official"),
    Pick("Apache HTTP Server (httpd)", "docker.io/library/httpd", ("webserver", "proxy"),
         "Apache httpd 2.4: web server, reverse proxy through mod_proxy, TLS through mod_ssl with certificates you supply",
         ("apache", "webserver", "proxy"), tag="2.4", licence="Apache-2.0", trust="official",
         aliases=("public.ecr.aws/docker/library/httpd",)),
    Pick("Traefik", "docker.io/library/traefik", ("proxy",),
         "Traefik 3: reverse proxy and load balancer for HTTP, TCP and UDP that finds its routes in Docker, Kubernetes "
         "or files; its own ACME client (Let's Encrypt); rate limits, IP allow-lists, basic and forward auth, a "
         "dashboard; it serves no files itself",
         ("traefik", "proxy", "tls"), tag="v3", licence="MIT", trust="official"),
    Pick("HAProxy", "docker.io/library/haproxy", ("proxy",),
         "HAProxy: TCP and HTTP load balancer and reverse proxy, TLS termination with certificates you supply",
         ("haproxy", "proxy"), tag="latest", licence="GPL-2.0", trust="official"),
    Pick("OpenResty", "docker.io/openresty/openresty", ("webserver", "proxy"),
         "OpenResty: nginx with LuaJIT and the ngx_lua modules, a web server and reverse proxy scripted in Lua; TLS "
         "with certificates you supply",
         ("openresty", "nginx", "webserver", "proxy"), tag="latest", licence="BSD-2-Clause", trust="project"),
    Pick("SWAG (Secure Web Application Gateway)", "ghcr.io/linuxserver/swag", ("webserver", "proxy"),
         "LinuxServer.io's nginx web server and reverse proxy with PHP, Certbot for Let's Encrypt and ZeroSSL (HTTP and "
         "DNS challenges), fail2ban with five jails (it needs --cap-add=NET_ADMIN) and ready-made proxy configurations",
         ("nginx", "webserver", "proxy", "tls", "bruteforce", "secure"), tag="latest", licence="GPL-3.0",
         trust="open source", aliases=("docker.io/linuxserver/swag", "lscr.io/linuxserver/swag", "quay.io/linuxserver.io/swag")),
    # -- mail servers -----------------------------------------------------------------------------------------------
    Pick("docker-mailserver", "docker.io/mailserver/docker-mailserver", ("mailserver",),
         "a complete mail server in one image: Postfix (Postscreen, DNSBL), Dovecot (IMAP, POP3, Sieve, quotas), Rspamd "
         "or Amavis with SpamAssassin, ClamAV, OpenDKIM, OpenDMARC, policyd-spf, Fail2ban, Postgrey, Fetchmail, SRS, "
         "LDAP or OAuth2 sign-in; Let's Encrypt certificates read from your own ACME client",
         ("postfix", "dovecot", "mailserver", "antispam", "antivirus", "mailauth", "imap", "smtp", "bruteforce", "tls",
          "secure"), tag="17", licence="MIT", trust="open source", aliases=("ghcr.io/docker-mailserver/docker-mailserver",)),
    Pick("mailcow: dockerized", "github.com/mailcow/mailcow-dockerized", ("mailserver",),
         "a mail server suite of 18 containers: Postfix, Dovecot, Rspamd (spam scores, greylisting, DKIM and ARC signing, "
         "SPF and DMARC checks), ClamAV, olefy (Office macro scanning), netfilter banning, ACME (Let's Encrypt), "
         "MTA-STS, SOGo webmail and an admin UI",
         ("postfix", "dovecot", "mailserver", "antispam", "antivirus", "mailauth", "imap", "smtp", "bruteforce", "tls",
          "webmail", "secure"), stack="https://docs.mailcow.email/getstarted/install/", licence="GPL-3.0", trust="project",
         note="a compose stack of 18 images: installed with its own script (generate_config.sh), not one pull"),
    Pick("Mailu", "github.com/mailu/mailu", ("mailserver",),
         "a mail server suite of about 13 containers: Postfix, Dovecot, Rspamd (anti-spam with auto-learn, greylisting, "
         "DMARC and SPF checks, DKIM signing), ClamAV, oletools, an nginx front with Let's Encrypt, DANE and MTA-STS, an "
         "admin UI and webmail",
         ("postfix", "dovecot", "mailserver", "antispam", "antivirus", "mailauth", "imap", "smtp", "tls", "webmail", "secure"),
         stack="https://setup.mailu.io/", licence="MIT", trust="project",
         note="a compose stack of about 13 images: its compose file is made at setup.mailu.io, not one pull"),
    Pick("Stalwart", "docker.io/stalwartlabs/stalwart", ("mailserver",),
         "an all-in-one mail and collaboration server in Rust (not Postfix): SMTP with DMARC, DKIM, SPF, ARC, DANE, "
         "MTA-STS and TLS reports; IMAP, JMAP, POP3, ManageSieve, CalDAV, CardDAV, WebDAV; its own spam and phishing "
         "filter; ACME certificates",
         ("stalwart", "mailserver", "antispam", "mailauth", "imap", "smtp", "tls"), tag="v1",
         licence="AGPL-3.0 core with a proprietary enterprise licence", trust="project",
         aliases=("ghcr.io/stalwartlabs/stalwart",)),
    Pick("Maddy", "docker.io/foxcpp/maddy", ("mailserver",),
         "one Go daemon in place of Postfix, Dovecot, OpenDKIM, OpenSPF and OpenDMARC: SMTP (MTA, MX, submission), IMAP "
         "(its storage still in beta), DKIM, SPF, DMARC, DANE, MTA-STS; spam checks through DNSBL or an rspamd of your own",
         ("maddy", "mailserver", "mailauth", "imap", "smtp"), tag="0.9", licence="GPL-3.0", trust="project",
         aliases=("ghcr.io/foxcpp/maddy",)),
    Pick("mox", "r.xmox.nl/mox", ("mailserver",),
         "one Go program: SMTP, IMAP4 and webmail, SPF, DKIM and DMARC with their reports, DANE, MTA-STS, per-user "
         "Bayesian junk filtering and sender reputation, automatic TLS through ACME",
         ("mox", "mailserver", "antispam", "mailauth", "imap", "smtp", "tls", "webmail"), tag="latest", licence="MIT",
         trust="project", note="its author calls the Docker way 'not recommended': the images are not rebuilt for new Go releases"),
    Pick("Poste.io (free edition)", "docker.io/analogic/poste.io", ("mailserver",),
         "an all-in-one mail server built on Haraka (not Postfix): Dovecot, Rspamd (SpamAssassin optional), ClamAV, "
         "Roundcube webmail, Let's Encrypt, automatic IP blocking and an admin UI",
         ("haraka", "mailserver", "antispam", "antivirus", "imap", "smtp", "tls", "webmail", "bruteforce"), tag="latest",
         licence="proprietary freeware (the free edition is for personal use)", trust="community",
         note="closed source, amd64 only; the PRO edition needs a login to poste.io's own registry"),
    Pick("iRedMail (dockerized)", "docker.io/iredmail/mariadb", ("mailserver",),
         "Postfix, Dovecot, Amavis with SpamAssassin, ClamAV, iRedAPD greylisting, Fail2ban, MariaDB, nginx, Roundcube",
         ("postfix", "dovecot", "mailserver", "antispam", "antivirus", "imap", "smtp", "bruteforce", "webmail"),
         tag="stable", licence="GPL-3.0", trust="community", penalty=0.4,
         note="abandoned: its repository was archived in 2023 and calls it a beta, not for production"),
)


def concept_words() -> list[tuple[str, str]]:
    """Every (word, concept id), the longest words first (a compound before its parts)."""
    pairs = [(w, cid) for cid, (_, words) in CONCEPTS.items() for w in words]
    return sorted(pairs, key=lambda p: (-len(p[0]), p[0]))


def kind_of(concept: str) -> str:
    return CONCEPTS.get(concept, ("word", ()))[0]
