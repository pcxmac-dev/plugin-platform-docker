# Changelog

## 0.5.1 (2026-11-26)

The search box's two hooks are asked only from the page. The user, 2026-11-26: "Yes, closed by default" (liminal-libs
1.107.0: a hook a plugin declares for no one is its page's alone).

- **`search` and `clear_search` are page-only** (`PAGE_ONLY_HOOKS`, beside its changes). A search sends its words to
  Docker Hub through the engine that answers, to Quay.io and to Artifact Hub, and replaces what the page's table
  keeps; the results forgotten empty it. Until now any plugin, and any program on this machine through the platform,
  could ask them. Another plugin's ask and an ask that names no one are refused (403) in words, and liminal-platform
  asks its login whether you are at the page (401 otherwise).
- `refresh`, `logs` and `details` stay reads anyone here may ask (`READ_HOOKS`), and the command line calls the code
  itself: that is not an ask.
- Every hook now says who may ask it, so the library's `conformance.warnings` is empty.

Tests: a search and its results forgotten refused to another plugin and to no one (no engine and no registry asked,
the table as it was), and done for the page; a test that no hook is left undeclared. They fail when either is taken
out of `PAGE_ONLY_HOOKS`, on liminal-libs 1.106.0 and on 1.107.0 alike. No new requirement: the word is liminal-libs
1.66.0's.

## 0.5.0 (2026-11-25)

On liminal-libs 1.97.0. Needs liminal-libs>=1.97.0.
- **An image built here** (SERVICE-INTERFACE.md §10): its DockerRuntime opts into the library's build
  (`builds=True`): a recipe whose part says `build` (Mercurial's hg serve) is offered on its engines, and its plan's
  work runs `docker build --pull=false --network=default --tag liminal/<owner>-<part>:<version> --label liminal=build
  --label liminal.build-sha=<context digest> -f Dockerfile -`, its context a tar on standard input holding the pinned
  files (each fetched and checked by its sha256 first) and the Dockerfile alone. The same pins are never built twice.
- **A recipe's command in a running part** (`hosted_run`, opted into: `ContainerHost.RUN_HOOKS`, plugin-only):
  `docker exec <container> <words>`, for a command the service's labelled recipe declares, asked by that service's
  plugin alone on your confirmation.
- Its API card names both calls (docker build, docker exec NAME WORDS).

## 0.4.1 (2026-11-25)

On liminal-libs 1.95.0's new hooks, where Docker gains from them. Needs liminal-libs>=1.95.0.
- **Where a service's data lives**, on each plan, in its engine's own word: `docker info`'s DockerRootDir
  (DockerRuntime with `read_root`), beside the target's words ("inside Liminal-Ubuntu's virtual disk", "on this
  machine's disk" in place of 0.4.0's fixed "/var/lib/docker"). Its API card names `docker info --format`.
- **Its stack named as every container plugin names it** (1.95.0's `containers.stack_of`, decided 2026-11-25): "wsl"
  for Docker in any Linux inside WSL 2, from either platform; "linux" for a Linux machine's own; "windows" for Docker
  Desktop. Unchanged in effect: 0.4.0 already said "wsl" there.
- The rest of 1.95.0 is the base's and reaches it unchanged: a secret its asker declares is handed over, an update that
  adds a part (an agent) is its own plan, a rollback needs every part's previous container. It declares no setting of
  yours (TARGET_SETTINGS): a Docker engine has no shared place of yours to name, and a named volume no size.

## 0.4.0 (2026-11-25)

Docker hosts Liminal's services: the first implementation of liminal-libs 1.93.0's one "run a service" interface
(`ContainerHost`, through the library's `DockerRuntime`), on Docker inside Liminal-Ubuntu first (decision 4: the WSL
plugin's docker, engine and user steps make it). Monday list items 34 and 35's foundation; service-containers-design
§2.3, §3 and §4.1, and the networking design's §5.1 and §8.4. Needs liminal-libs>=1.93.0.
- **Its targets**: each engine of this machine (Docker inside Liminal's WSL distributions, this machine's docker, a
  context or host whose endpoint is this machine's), ready while it answers. A stopped distribution's engine is
  "stopped" and is asked nothing (a look never starts it, and no plan starts it either: refused before any command); an
  engine on another machine is "not here" (a service's data stays on this machine); a Windows engine is left to the
  Windows containers plugin; Docker Desktop's Linux engine cannot take a service's routed network yet (its own limit).
- **Its plans, in its own words**, approved on the page (its Waiting for your answer table, or liminal-platform 0.37.0's
  dialog), carried out as its own work: the image pulled by digest and checked, the named volumes made or found, the
  service's own network with the subnet the Windows firewall hands out (`trusted_host_interfaces=eth0`), each container
  made by digest with `--restart no`, a memory limit, its labels and its fixed address, a secret by environment alone
  (`-e NAME`, its value crossing into WSL through WSLENV), seeds into a new volume, the firewall's route, the
  distribution held up through its WSL plugin, then started and waited for. An update backs up first and keeps the
  previous container; an unhealthy one is undone; Remove keeps the data; Delete its data is asked twice.
- **Its page** gains Liminal's services, Waiting for your answer (Approve…, each accept in turn; Decline…), Service plugins
  (Let it…, Stop letting it…: the grant once per service plugin and engine) and Kept data (Forget…, asked twice). They
  read the engines only once a service plugin asked, a grant, a plan or a work is held, more than one engine answers, or
  the shown engine's listings name a service's container or volume; otherwise its page asks nothing more than before.
- **Its own changes guarded**: Remove… of a service's container is refused, pointing at its owner's page (start and stop
  stay allowed). Its own change hooks (choose_engine, container, remove_container, pull, remove_image) are its page's
  alone (PAGE_ONLY_HOOKS: the networking design's §8.1, N1 a), and its reads are declared (READ_HOOKS: refresh, logs,
  details).
- **The runner**: `engines.service_run`, windowless, takes standard input, an environment laid over its own (Liminal's
  variables and every plugin's declared pairs left out), bytes, and a file for a backup. A test's plain stand-in runner
  has every service command refused rather than run for real.
- Its API card names every command a service's plans run (create, cp, rename, run, exec, inspect, volume and network
  create, inspect and rm, image inspect), each with what it is used for.
- Tests: `test_services.py` (Docker inside Liminal-Ubuntu on the library's FakeDocker and stand-in firewall, attached to
  a real apps.App: the exact argv through WSL, the canary secret, the stopped distribution, the guards, the conformance
  sequence); each of its 8 gates taken out once made a test fail.

## 0.3.2 (2026-11-24)

An image's pull can be cancelled, and ends when the plugin is turned off or the platform stops (the review of 2026-11-21, item 26, finding 17: its job had no Cancel, and `detach` left `docker pull` running for up to `PULL_S`, 1,800 s). `CANCEL_HOOKS = ("pull",)`, so the platform's page offers Cancel on a pull's job and its stop asks it to end; `engines.stream` takes a `stop` it looks at every 0.25 s while the command runs and, once asked, kills it (`Cancelled`); `pull` registers each pull's stop, set by `detach` and `app_stopping`, and says "cancelled" (not ok) with docker keeping the layers that came. A pull asked without a job is streamed too, so turning the plugin off ends it as well.

## 0.3.1 (2026-11-15)

Drawn under the platform's Virtualization plugins section, in the list on the left (the user: "platform needs a virtualization plugins section"; "just like cloud plugins"; "docker, libvirt, kubernetes, lxc should be in virtualization"): `SECTION = "virtualization"`, liminal-libs 1.51.0's machine-plugin attribute. liminal-platform 0.26.0 draws it; an older platform keeps the plugin under Machine plugins. Nothing else changes.

## 0.3.0 (2026-11-11)

Its API on its page (plugin API 2.2, liminal-libs 1.49.0; the user: "each plugin should reflect the the API its attached
to, and present links that provide documentation, the plugin interface should more or less contain what it already has,
BUT, it should also expose more of what the API is about"). Needs liminal-libs>=1.49.0.

- `apis` (apis.py): five cards, each read from its maker's pages on 2026-11-11: the **Docker CLI and Engine API** (the
  docker command and the engine's REST API under it: 17 links, from the CLI and Engine API references to the release
  notes, the OpenAPI file and Docker Desktop's license; 23 parts, 7 of them used; 24 commands, the 14 it runs each named
  with the Engine API call it is), the **Docker Hub API** (11 parts: repositories used, the website's undocumented search
  when its setting is on; its per-minute limit headers and the pull limits in numbers), **Quay.io's API** (23 parts from
  its discovery document: search and tags used), **Artifact Hub's API** (9 parts: packages used) and the **OCI
  Distribution** API every registry speaks (tags listed, the anonymous token, the HEAD that reads Docker Hub's pulls
  left). Each call says what the plugin makes it for, a change is marked as one, and none costs.
- `api_facts()`: what it already holds, asking nothing: the engines as last read (the shown one's engine and client
  versions, when), each registry's requests made and a host that asked to wait (the registries' client now counts its
  requests by host), Docker Hub's anonymous pulls left as the last search read them.
- Tests: the cards are sound; they name every docker command and every registry address the plugin sends (read from
  the stand-ins as it sends them) and claim none it does not; the facts ask nothing; with LIMINAL_VENDOR_PAGES=1, every
  address on the cards answers (all did on 2026-11-11).

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
