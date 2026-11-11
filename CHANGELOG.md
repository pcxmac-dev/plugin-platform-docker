# Changelog

## 0.2.0 (2026-11-11)

Find an image for anything, see what it provides, and pull it with its progress shown (the user, 2026-11-10: "lets roll
in a way to import docker images (from various docker repos) with a search that can find things like nginx webserver or
postfix secure file server w/ all the anti-spam+++"; "there needs to be enough docker description in order to understand
what is being provided"; "i want to be able to get a docker image for anything"; of Docker Hub: "Engine only"; of the
roles: mail server, no file server yet; of stacks: "Single images now").

- **Find an image** (the first table, a search box above it on liminal-platform 0.19.0): a search's words read
  (`query.py`: the roles, products, features and qualities it knows, the user's other words kept, so anything can be
  searched), then asked at once of Docker Hub through the engine that answers (`docker search`: the documented route),
  Quay.io and Artifact Hub (their documented APIs), with Liminal's picks for web servers, reverse proxies and mail servers
  (`catalog.py`: what each provides, its references, its tag, its licence and status; compose stacks listed, never
  pulled). Merged by reference; Docker Hub's best enriched through its documented repository and tags API (pulls, when
  updated, categories; a repository holding no tag, the way spam looks, left out and said); ranked by what of the search
  they cover, then trust, popularity, freshness and a pick of the role asked, less what speaks against them (deprecated,
  a relay where a whole mail server is asked, a Kubernetes part where a server is, a sign-in needed); each with its
  reasons in words. With no engine answering, Docker Hub is said as not searched and the rest answer.
- **Details** of any image: where from and by whom, why it ranks there, what it provides, its description and its
  README's first lines (its publisher's words, as plain text: no markup, images or link addresses), its newest tags
  with their dates, sizes and platforms (Docker Hub's and Quay's APIs; any other registry's through the OCI distribution
  API with the anonymous token it asks for), and the reference it is pulled as.
- **Pull** from a result (its tag the pick's advice, or what the registry holds): a job on liminal-platform 0.19.0
  (`JOB_HOOKS`), docker's lines shown as they come (`engines.stream`, windowless); the confirmation says Docker Hub's
  anonymous pulls are limited, and the table says how many are left from here (its documented check: a HEAD, which spends
  no pull; the address it echoes is never kept or said). A compose stack is refused in words.
- Docker Hub's website search (undocumented: Docker's terms allow automated access only through documented APIs) only
  when the setting DOCKER_HUB_WEBSITE_SEARCH is on (kept through the platform's login; off unless set).
- The registries' requests (`sources.py`): https only, the plugin's own user agent (nothing of the user's), a turn per
  host, a search kept 10 minutes and a detail 5, a host that asks to wait (429, Artifact Hub's 403) left alone until then,
  answers cut at 4 MB; detached, what they said is forgotten. No thread or process is left running between asks.
- `python -m plugin_platform_docker search WORDS... [--where all|docker-hub|quay|artifact-hub|catalog]`, `details IMAGE`;
  `pull` prints docker's lines as they come.
- Mended before release (a review of it, each finding put to a skeptic): a search asks the engine as every change does (a
  distribution stopped since the last look is never started by a search); redirects followed only to https on the same
  host, an answer given at most 20 s in all, a publisher's text read from its start only (quick whatever it holds); the tag
  offered is 'latest' when the repository holds it (asked by name) and never a signature, an attestation or a development
  build; a source late at the deadline stops between its terms, what it found kept; results merged in one order; a
  project's own name ("rspamd", "clamav") searched as typed, asking for that project, not a role; "secure" alone is no
  search; a search of one registry keeps its own references; Details reads its parts apart, another registry's tags said
  in its order.

## 0.1.0 (2026-11-08)

Its icon is Docker's whale with its containers, drawn in the library's line (liminal-libs 1.33.0's `docker`; the user: "for the docker and kubernetes plugins, use their respective logos"). Needs liminal-libs>=1.33.0.

The first release (the user: "and then i need a kubernetes and docker plugin for platform"): Docker's engines as a
machine plugin of the platform, on liminal-libs 1.30.0's `docker.py`.

- Every engine `docker.instances` knows (this machine's docker command and its contexts, `LIMINAL_DOCKER_HOST`, Docker
  inside Liminal's WSL distributions as the WSL plugins offer it), each one's versions and state in a table.
- The engine shown (chosen on the page): its containers, images, volumes and networks as tables.
- Confirmed forms: a container started, stopped, restarted or removed; an image pulled or removed; a container's last
  log lines. A running container's removal, and an image's a container was made from, are asked again (`force`).
- Valid when one engine answers; with none, why, and how to have one.
- An engine in a stopped WSL distribution is never asked (no `wsl -d` until WSL lists it running); what was read is
  kept 30 s; nothing runs between asks; detached, what was read goes.
- On this PC (2026-11-08): docker is not on Windows' PATH; the one engine is the WSL Ubuntu plugin's, in Liminal-Ubuntu
  (stopped: not asked), so the plugin says it is not valid until the distribution runs.
