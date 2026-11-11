# plugin-platform-docker

Docker for Liminal: every Docker engine here, each one's version and whether it runs, the containers, images, volumes
and networks of the engine chosen on the platform's page, and the changes the page confirms.

The user's words (2026-11-08): "and then i need a kubernetes and docker plugin for platform"; earlier, of the
platform: "basically the platform is the interface for the software/hardware which facilitates the liminal framework".

## What it does

A machine plugin of the platform (`liminal_libs.machines.MachinePlugin`, plugin API 2.2, its icon the database: the
library's icons.js has no box yet) over the library's `docker.py`:

- **The engines**: every one `liminal_libs.docker.instances` knows: this machine's docker command (Docker Desktop,
  Rancher Desktop; `LIMINAL_DOCKER_COMMAND` for nerdctl or podman) and its contexts (`docker context ls`: a VPS over
  SSH), the host `LIMINAL_DOCKER_HOST` names, and Docker inside Liminal's WSL distributions, offered by the WSL plugins
  (`wsl-ubuntu`: `wsl -d Liminal-Ubuntu --exec docker`). Each one's engine and client versions, its system, and whether
  it runs, in the Docker engines table.
- **The engine shown** (chosen above the engines' table, kept until the platform restarts; the first that answers
  otherwise): its containers (name, image, state, ports, when made; Liminal's own services marked), images (size, when
  made, the containers made from each), volumes (driver, the containers using each) and networks (driver, how many
  containers are on each), each a table.
- **Find an image** for anything (0.2.0): the words typed in the search box above the first table are read (roles,
  products, features and qualities it knows: "nginx web server", "postfix mail server with anti-spam"; anything else by its
  own words: "postgres", "home assistant") and asked at once of Docker Hub through the engine that answers (`docker search`,
  the documented route; with none answering, Docker Hub is said as not searched), Quay.io and Artifact Hub (their documented
  APIs), with Liminal's picks for web servers, reverse proxies and mail servers. Each result says what it provides, where
  it comes from and by whom, and why it ranks where it does; **Details** reads its description, its README's first lines
  (as plain text) and its newest tags with their dates, sizes and platforms; **Pull…** pulls it as a job, docker's lines
  shown as they come (liminal-platform 0.19.0). A compose stack (mailcow, Mailu) is listed with its install page, never
  pulled. Docker Hub's website search (undocumented) is asked only when the setting DOCKER_HUB_WEBSITE_SEARCH is on.
- **The changes**, each through a form the page confirms first: a container started, stopped (given 20 s to end on its
  own, then killed) or restarted; a container removed (its image and volumes stay; a running one only once accepted
  again: it is killed first); an image pulled; an image removed (one a container was made from only once accepted
  again); a container's last lines read (its output and its errors in the order written, at this machine's time).

It is valid when at least one engine answers. With none: "no Docker engine here: install Docker Desktop, or Docker
inside a WSL distribution through the WSL plugins"; with engines that do not answer, each one's reason.

**Never started to look.** An engine reached through WSL is asked only while WSL lists its distribution running
(`wsl --list --verbose`, which starts nothing): any `wsl -d` boots a stopped distribution, so a stopped one is said as
stopped and its Docker is read once it runs (from the WSL plugin's terminal, say). A change refuses then too. One a WSL
plugin offers in a distribution that is not Liminal's own is not asked at all. Nothing runs on its own: the plugin
reads when the platform asks, keeps what it read 30 s (the page asks every few seconds; a change reads again at once;
Read again asks now), holds no process and no thread between asks, and forgets what it read when detached.

Every command runs windowless (`CREATE_NO_WINDOW` on Windows), without this process's standard input, its output read
as UTF-8 (a container's log may hold any bytes), through the library's `Docker` (the plugin's `Engine` adds the
listings, a restart, an image's removal and a log with its error stream).

## Its API

What it attaches to, as its page shows it (plugin API 2.2: `apis.py`, read from the makers' pages on 2026-11-11), each
API's parts and calls, those the plugin uses first and the rest after them:

- **Docker CLI and Engine API** (Docker, Inc.): the `docker` command and the engine's REST API under it. The
  [CLI reference](https://docs.docker.com/reference/cli/docker/), the
  [Engine API reference](https://docs.docker.com/reference/api/engine/version/v1.56/) (and its
  [OpenAPI file](https://docs.docker.com/reference/api/engine/version/v1.56.yaml)),
  [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/), the
  [release notes](https://docs.docker.com/engine/release-notes/).
- **Docker Hub API**: the [reference](https://docs.docker.com/reference/api/hub/latest/), its
  [usage and limits](https://docs.docker.com/docker-hub/usage/) and [pull limits](https://docs.docker.com/docker-hub/usage/pulls/),
  [Docker's status](https://www.dockerstatus.com/).
- **Quay.io API**: [its API](https://docs.quay.io/api/) and [explorer](https://docs.quay.io/api/swagger/), the
  [Project Quay API guide](https://docs.projectquay.io/api_quay.html).
- **Artifact Hub API**: [its API](https://artifacthub.io/docs/api/) and [its documentation](https://artifacthub.io/docs/).
- **OCI Distribution** (any registry's API): the
  [specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md) and the
  [token authentication](https://distribution.github.io/distribution/spec/auth/token/) a public image's anonymous token
  follows.

`api_facts()` says what it learned while it ran, asking nothing: the engines as last read and their versions, each
registry's requests and a host that asked to wait, Docker Hub's anonymous pulls left as the last search read them.
`LIMINAL_VENDOR_PAGES=1 pytest tests/test_apis.py` checks that every address on the cards still answers.

## Its hooks

`present` (an engine is known), `status` (the summary, the facts, `tables`, `forms`, `actions`), `search(query, where)`
(images for anything, kept for the page's table), `details(image)`, `clear_search()`, `choose_engine(engine)`
(the engine the tables show), `refresh()` (every engine read again now), `container(engine, name, action)` (`action`:
`start`, `stop` or `restart`), `remove_container(engine, name, force)`, `logs(engine, name, lines)` (100 lines unless
given, at most 2,000), `pull(engine, image, log)` (a job: `log` the platform's panel), `remove_image(engine, image, force)`. A refusal that `force` accepts
names it (`accept`), and the page asks a second confirmation before sending it.

## From the command line

```
python -m plugin_platform_docker status
python -m plugin_platform_docker engines
python -m plugin_platform_docker containers [ENGINE]        # images, volumes, networks alike
python -m plugin_platform_docker logs wsl-ubuntu web 200
python -m plugin_platform_docker stop wsl-ubuntu web        # start, restart alike
python -m plugin_platform_docker remove wsl-ubuntu web [--force]
python -m plugin_platform_docker pull wsl-ubuntu nginx:1.27
python -m plugin_platform_docker rmi wsl-ubuntu nginx:1.27 [--force]
python -m plugin_platform_docker search postfix mail server with anti-spam [--where quay]
python -m plugin_platform_docker details mailserver/docker-mailserver
```

An engine is named as the Docker engines table names it: `local`, `context:<name>`, `host`, or a WSL plugin's name.
`--force` accepts what the page would ask again.
