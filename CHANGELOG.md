# Changelog

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
