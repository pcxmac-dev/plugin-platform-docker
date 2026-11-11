"""What the Docker plugin attaches to (plugin API 2.2; the user, 2026-11-11: "each plugin should reflect the the API its
attached to, and present links that provide documentation ... it should also expose more of what the API is about"):
the docker command and the Engine API under it, Docker Hub's API, Quay.io's API, Artifact Hub's API and the OCI
distribution API every registry speaks. Each part of each API is named with what the plugin does with it, each call it
makes with what it makes it for, and the notable calls it does not make; every address was read on its maker's pages on
2026-11-11 (liminal_libs.sources.apis.dead_links checks them, LIMINAL_VENDOR_PAGES=1)."""
from __future__ import annotations

from liminal_libs.sources.apis import Api, Area, Call, Link

VERIFIED = "2026-11-11"
CLI = "Docker CLI and Engine API"
HUB = "Docker Hub API"
QUAY = "Quay.io API"
ARTIFACTHUB = "Artifact Hub API"
OCI = "OCI Distribution (registry API)"

_REF = "https://docs.docker.com/reference/cli/docker/"
_HUB_OPS = "https://docs.docker.com/reference/api/hub/latest/operations/"
_OCI_SPEC = "https://github.com/opencontainers/distribution-spec/blob/main/spec.md"


def _cli(path: str) -> str:
    return _REF + path + "/"


DOCKER_CLI = Api(
    name=CLI, maker="Docker, Inc.", kind="command",
    about=("The docker command and the Docker Engine API it speaks: the engine's REST API over its socket (a Unix socket, a "
           "Windows named pipe, SSH or TCP), which runs containers and keeps images, volumes and networks. The plugin runs the "
           "docker command (this machine's, a context's, a host's, or inside a WSL distribution of Liminal's own), never the "
           "API directly: each command is one or two of the API's calls, named beside it."),
    base="docker (or wsl -d Liminal-<distribution> --exec docker; --context NAME, -H HOST)",
    version="the docker CLI's JSON listings (--format '{{json .}}'); read against Docker Engine 29, Engine API v1.56",
    auth=("none of its own: the engine's socket's permissions (root or the docker group on Linux, docker-users on Windows), a "
          "context's SSH key or TLS certificates; a registry's sign-in (docker login) is the engine's, never the plugin's"),
    limits=("none on the engine (it is local); what it pulls counts against the registry's limits (Docker Hub: 100 pulls per "
            "6 hours per IPv4 address or IPv6 /64 without an account)"),
    costs=("Docker Engine and the CLI are free (Apache 2.0); Docker Desktop is free for personal use, education, non-commercial "
           "open source and small businesses (fewer than 250 employees and less than $10 million a year), a paid subscription "
           "otherwise"),
    links=(
        Link("Docker Engine documentation", "https://docs.docker.com/engine/", "docs"),
        Link("docker CLI reference", _REF, "reference"),
        Link("Engine API reference (v1.56)", "https://docs.docker.com/reference/api/engine/version/v1.56/", "reference"),
        Link("Engine API: versions and SDKs", "https://docs.docker.com/reference/api/engine/", "guide"),
        Link("Docker contexts", "https://docs.docker.com/engine/manage-resources/contexts/", "guide"),
        Link("Install Docker Engine", "https://docs.docker.com/engine/install/", "guide"),
        Link("Docker Desktop's WSL 2 backend", "https://docs.docker.com/desktop/features/wsl/", "guide"),
        Link("Protect the Docker daemon socket", "https://docs.docker.com/engine/security/protect-access/", "auth"),
        Link("Linux post-installation (the docker group)", "https://docs.docker.com/engine/install/linux-postinstall/", "auth"),
        Link("Docker Desktop license agreement", "https://docs.docker.com/subscription-billing/desktop-license/", "pricing"),
        Link("Engine API version history", "https://docs.docker.com/reference/api/engine/version-history/", "changelog"),
        Link("Docker Engine release notes", "https://docs.docker.com/engine/release-notes/", "changelog"),
        Link("Engine API v1.56 (OpenAPI)", "https://docs.docker.com/reference/api/engine/version/v1.56.yaml", "spec"),
        Link("Docker Desktop", "https://docs.docker.com/desktop/", "tool"),
        Link("Engine SDKs", "https://docs.docker.com/reference/api/engine/sdk/", "sdk"),
        Link("docker/cli", "https://github.com/docker/cli", "source"),
        Link("moby/moby (the engine)", "https://github.com/moby/moby", "source"),
    ),
    areas=(
        Area("Containers", "docker container (the Engine API's Containers): made, run, started, stopped, inspected, removed",
             _cli("container"), covered="listed with their state, ports and age; started, stopped, restarted and removed once "
                                        "confirmed; their last log lines read"),
        Area("Images", "docker image (Images): pulled, built, tagged, pushed, removed", _cli("image"),
             covered="listed with their size and the containers made from each; pulled as a job, removed once confirmed"),
        Area("Volumes", "docker volume (Volumes): the containers' lasting storage", _cli("volume"),
             covered="listed with the containers using each"),
        Area("Networks", "docker network (Networks): the networks containers join", _cli("network"),
             covered="listed with how many containers are on each"),
        Area("Contexts", "docker context: the engines the CLI knows (this machine's, a VPS over SSH), kept by the CLI itself",
             _cli("context"), covered="each context is an engine of the Docker engines table"),
        Area("System", "docker version, docker system (info, df, events, prune): the engine itself", _cli("system"),
             covered="each engine's and its client's versions, and whether it answers"),
        Area("Image search", "docker search: Docker Hub searched by the engine (GET /images/search)", _cli("search"),
             covered="Docker Hub's results in Find an image"),
        Area("Inspect", "docker inspect: any object's whole description, as JSON", _cli("inspect")),
        Area("Exec", "docker exec (Exec): a command run inside a running container", _cli("container/exec")),
        Area("Build", "docker buildx and docker builder (the engine's /build): images made from a Dockerfile", _cli("buildx")),
        Area("Compose", "docker compose: several containers defined together in a file and run as one", _cli("compose")),
        Area("Registry sign-in", "docker login and logout (the engine's /auth): a registry's account", _cli("login")),
        Area("Manifests and trust", "docker manifest and docker trust: multi-platform lists and signed images", _cli("manifest")),
        Area("Plugins", "docker plugin (Plugins): the engine's own plugins (volume and network drivers)", _cli("plugin")),
        Area("Swarm", "docker swarm, node, service, stack, secret and config (Swarm, Nodes, Services, Tasks, Secrets, Configs): "
                      "engines clustered", _cli("swarm")),
        Area("Checkpoints", "docker checkpoint: a running container's state saved (experimental)", _cli("checkpoint")),
        Area("Scout", "docker scout: an image's packages and their known vulnerabilities", _cli("scout")),
        Area("Model Runner", "docker model: AI models pulled and run by the engine", _cli("model")),
        Area("MCP Toolkit", "docker mcp: MCP servers run as containers", _cli("mcp")),
        Area("Hardened Images", "docker dhi: Docker's hardened images", _cli("dhi")),
        Area("Offload", "docker offload: builds and containers run on Docker's cloud", _cli("offload")),
        Area("Debug and init", "docker debug (a shell in any container) and docker init (a project's Docker files made)",
             _cli("debug")),
        Area("Docker Desktop", "docker desktop: Docker Desktop started, stopped and updated", _cli("desktop")),
    ),
    calls=(
        Call("docker version", "the client's and the engine's versions, as JSON (GET /version)", "System",
             used="each engine's version and whether it answers (the Docker engines table)", docs=_cli("version")),
        Call("docker context ls", "the CLI's contexts, as JSON (no engine asked: the CLI's own store)", "Contexts",
             used="an engine for each context", docs=_cli("context/ls")),
        Call("docker ps -a --no-trunc", "every container, stopped ones too (GET /containers/json?all=1)", "Containers",
             used="the Containers table", docs=_cli("container/ls")),
        Call("docker images --no-trunc", "the images (GET /images/json)", "Images", used="the Images table",
             docs=_cli("image/ls")),
        Call("docker volume ls", "the volumes (GET /volumes)", "Volumes", used="the Volumes table", docs=_cli("volume/ls")),
        Call("docker network ls --no-trunc", "the networks (GET /networks)", "Networks", used="the Networks table",
             docs=_cli("network/ls")),
        Call("docker logs --tail N --timestamps NAME", "a container's last lines, its output and its errors "
             "(GET /containers/{id}/logs)", "Containers", used="Logs: a container's last lines", docs=_cli("container/logs")),
        Call("docker start NAME", "a stopped container started (POST /containers/{id}/start)", "Containers",
             used="Start… a container", docs=_cli("container/start"), writes=True),
        Call("docker stop -t 20 NAME", "a container stopped, killed after 20 s (POST /containers/{id}/stop)", "Containers",
             used="Stop… a container", docs=_cli("container/stop"), writes=True),
        Call("docker restart -t 20 NAME", "a container stopped and started again (POST /containers/{id}/restart)",
             "Containers", used="Restart… a container", docs=_cli("container/restart"), writes=True),
        Call("docker rm NAME", "a container removed, -f killing a running one first (DELETE /containers/{id})", "Containers",
             used="Remove… a container (a running one only once accepted again)", docs=_cli("container/rm"), writes=True),
        Call("docker pull IMAGE", "an image downloaded from its registry (POST /images/create)", "Images",
             used="Pull… an image, as a job", docs=_cli("image/pull"), writes=True),
        Call("docker rmi IMAGE", "an image's tag removed, -f when a container was made from it (DELETE /images/{name})",
             "Images", used="Remove… an image (one a container was made from only once accepted again)",
             docs=_cli("image/rm"), writes=True),
        Call("docker search --no-trunc --limit 40 TERM", "Docker Hub searched by the engine (GET /images/search)",
             "Image search", used="Find an image: Docker Hub's results", docs=_cli("search")),
        Call("docker run IMAGE", "a container made and started (POST /containers/create, then start)", "Containers",
             docs=_cli("container/run"), writes=True),
        Call("docker exec NAME COMMAND", "a command run in a running container (POST /containers/{id}/exec)", "Exec",
             docs=_cli("container/exec"), writes=True),
        Call("docker inspect NAME", "an object's whole description (GET /containers/{id}/json)", "Inspect",
             docs=_cli("inspect")),
        Call("docker stats", "the containers' processor, memory, network and disk use (GET /containers/{id}/stats)",
             "Containers", docs=_cli("container/stats")),
        Call("docker system df", "the disk the engine's images, containers and volumes take (GET /system/df)", "System",
             docs=_cli("system")),
        Call("docker system prune", "stopped containers, unused networks and dangling images removed", "System",
             docs=_cli("system"), writes=True),
        Call("docker compose up", "a compose file's containers made and started", "Compose", docs=_cli("compose"),
             writes=True),
        Call("docker buildx build", "an image built from a Dockerfile (POST /build)", "Build", docs=_cli("buildx"),
             writes=True),
        Call("docker image push IMAGE", "an image uploaded to its registry (POST /images/{name}/push)", "Images",
             docs=_cli("image/push"), writes=True),
        Call("docker login", "a registry's account signed in to (POST /auth)", "Registry sign-in", docs=_cli("login"),
             writes=True),
    ),
    verified=VERIFIED)

DOCKER_HUB = Api(
    name=HUB, maker="Docker, Inc.", kind="rest",
    about=("Docker Hub's own API: its repositories and their tags, and an organization's members, groups, tokens and audit "
           "logs. Public repositories are read without an account. The plugin reads what an image is (its pulls, stars, "
           "dates, categories and descriptions) and its newest tags; Docker Hub is searched through the engine "
           "(docker search), and through the website's own search only when its setting is on."),
    base="https://hub.docker.com", version="2-beta (the reference's own name)",
    auth=("none for public repositories (anonymous: the plugin never signs in); a personal or organization access token, "
          "exchanged for a bearer token (POST /v2/auth/token), for the rest"),
    limits=("a per-minute limit said in every answer (X-RateLimit-Limit, -Remaining, -Reset; 429 with Retry-After past it); "
            "pulls apart: 100 per 6 hours per IPv4 address or IPv6 /64 without an account, 200 for a Personal account, "
            "unlimited for Pro, Team and Business (fair use); an abuse limit of thousands of requests a minute per address"),
    costs=("nothing to read public repositories; a Personal account is free (one private repository), Pro, Team and Business "
           "are paid subscriptions"),
    links=(
        Link("Docker Hub API reference", "https://docs.docker.com/reference/api/hub/latest/", "reference"),
        Link("Docker Hub documentation", "https://docs.docker.com/docker-hub/", "docs"),
        Link("Docker Hub search", "https://docs.docker.com/docker-hub/image-library/search/", "guide"),
        Link("Usage and limits", "https://docs.docker.com/docker-hub/usage/", "limits"),
        Link("Pull usage and limits", "https://docs.docker.com/docker-hub/usage/pulls/", "limits"),
        Link("Pricing", "https://www.docker.com/pricing/", "pricing"),
        Link("Docker status", "https://www.dockerstatus.com/", "status"),
        Link("Docker Hub API changelog", "https://docs.docker.com/reference/api/hub/changelog", "changelog"),
        Link("Docker Hub API (OpenAPI)", "https://docs.docker.com/reference/api/hub/latest.yaml", "spec"),
        Link("Docker Hub", "https://hub.docker.com/", "console"),
        Link("hub-tool (Docker Hub's CLI, experimental)", "https://github.com/docker/hub-tool", "tool"),
        Link("Docker Terms of Use", "https://www.docker.com/legal/docker-terms-use/", "terms"),
    ),
    areas=(
        Area("Repositories", "a namespace's repositories, each one's description, counts and dates, its tags",
             _HUB_OPS + "GetRepository/", covered="what an image is (pulls, stars, dates, categories, descriptions) and its "
                                                  "newest tags, for Find an image and Details"),
        Area("Authentication", "sign-in (a password, a second factor) and bearer tokens", _HUB_OPS + "AuthCreateAccessToken/"),
        Area("Personal access tokens", "a user's tokens made, listed, changed and removed", _HUB_OPS + "getV2AccessTokens/"),
        Area("Audit logs", "an account's events and their actions", _HUB_OPS + "AuditLogs_ListAuditLogs/"),
        Area("Organization settings", "an organization's settings (restricted images)", _HUB_OPS + "getV2OrgsByNameSettings/"),
        Area("Organization members", "an organization's members, their roles, an export", _HUB_OPS + "getV2OrgsByOrgNameMembers/"),
        Area("Groups (teams)", "an organization's groups and their members", _HUB_OPS + "getV2OrgsByOrgNameGroups/"),
        Area("Invites", "invitations to an organization", _HUB_OPS + "getV2OrgsByOrgNameInvites/"),
        Area("SCIM", "users provisioned from an identity provider (SCIM 2.0)", _HUB_OPS + "getV2Scim20Users/"),
        Area("Organization access tokens", "an organization's own tokens", _HUB_OPS + "getV2OrgsByNameAccessTokens/"),
        Area("Website search (undocumented)", "the search Docker Hub's own pages use: not part of the documented API",
             covered="asked only when the setting DOCKER_HUB_WEBSITE_SEARCH is on (Docker's terms allow automated access "
                     "through documented APIs)"),
    ),
    calls=(
        Call("GET /v2/namespaces/{namespace}/repositories/{repository}", "a repository: its descriptions, pulls, stars, "
             "dates and categories", "Repositories", used="Find an image (its best results enriched) and Details",
             docs=_HUB_OPS + "GetRepository/"),
        Call("GET /v2/namespaces/{namespace}/repositories/{repository}/tags", "its tags, newest first, with their sizes and "
             "platforms", "Repositories", used="Details: its newest tags; the tag a result offers",
             docs=_HUB_OPS + "ListRepositoryTags/"),
        Call("GET /v2/namespaces/{namespace}/repositories/{repository}/tags/{tag}", "one tag, by its name (404: not there)",
             "Repositories", used="whether a repository holds a tag (latest, a pick's)", docs=_HUB_OPS + "GetRepositoryTag/"),
        Call("GET /api/search/v4", "the website's own search (undocumented)", "Website search (undocumented)",
             used="Find an image, only when DOCKER_HUB_WEBSITE_SEARCH is on"),
        Call("GET /v2/namespaces/{namespace}/repositories", "a namespace's repositories", "Repositories",
             docs=_HUB_OPS + "listNamespaceRepositories/"),
        Call("HEAD /v2/namespaces/{namespace}/repositories/{repository}/tags/{tag}", "whether a tag is there, without its "
             "body", "Repositories", docs=_HUB_OPS + "headV2NamespacesByNamespaceRepositoriesByRepositoryTagsByTag/"),
        Call("POST /v2/namespaces/{namespace}/repositories", "a repository made", "Repositories",
             docs=_HUB_OPS + "CreateRepository/", writes=True),
        Call("POST /v2/auth/token", "a bearer token for an access token", "Authentication",
             docs=_HUB_OPS + "AuthCreateAccessToken/"),
        Call("POST /v2/access-tokens", "a personal access token made", "Personal access tokens",
             docs=_HUB_OPS + "postV2AccessTokens/", writes=True),
        Call("GET /v2/auditlogs/{account}", "an account's audit log", "Audit logs", docs=_HUB_OPS + "AuditLogs_ListAuditLogs/"),
        Call("GET /v2/orgs/{org_name}/members", "an organization's members", "Organization members",
             docs=_HUB_OPS + "getV2OrgsByOrgNameMembers/"),
    ),
    verified=VERIFIED)

QUAY_IO = Api(
    name=QUAY, maker="Red Hat (Project Quay)", kind="rest",
    about=("Quay.io's API: its repositories, tags, manifests and their security scans, builds and their triggers, robot "
           "accounts, organizations and teams. Public repositories are read without an account. The plugin searches it and "
           "reads an image's newest tags."),
    base="https://quay.io", version="v1",
    auth=("none for public repositories; an OAuth 2 access token (an application's, made in an organization) as a bearer "
          "token for the rest"),
    limits=("Quay caps the requests a second from each IP address (no number published; 429 past it); the plugin asks at most "
            "one every half second"),
    costs="nothing for public repositories; private repositories by plan",
    links=(
        Link("Quay API", "https://docs.quay.io/api/", "docs"),
        Link("API explorer", "https://docs.quay.io/api/swagger/", "reference"),
        Link("Project Quay API guide", "https://docs.projectquay.io/api_quay.html", "guide"),
        Link("Working with tags", "https://docs.quay.io/guides/tag-operations.html", "guide"),
        Link("HTTP status 429", "https://docs.quay.io/issues/429.html", "limits"),
        Link("Plans", "https://quay.io/plans/", "pricing"),
        Link("Status", "https://status.quay.io/", "status"),
        Link("API discovery (Swagger)", "https://quay.io/api/v1/discovery", "spec"),
        Link("quay/quay", "https://github.com/quay/quay", "source"),
    ),
    areas=(
        Area("Search", "repositories (and more) found by words", covered="Find an image: Quay.io's results"),
        Area("Tags", "a repository's tags: listed, moved, restored, removed", "https://docs.quay.io/guides/tag-operations.html",
             covered="Details: a Quay image's newest tags"),
        Area("Repositories", "repositories listed, made, changed and removed"),
        Area("Manifests", "a manifest and its labels"),
        Area("Security scans", "a manifest's known vulnerabilities"),
        Area("Builds", "builds from a Dockerfile, their status and logs"),
        Area("Build triggers", "builds started by a source repository's pushes"),
        Area("Repository notifications", "events sent on (a push, a build, a vulnerability)"),
        Area("Permissions", "who may read or write a repository"),
        Area("Default permissions", "permissions given to an organization's new repositories (prototypes)"),
        Area("Robot accounts", "accounts for machines"),
        Area("Organizations", "organizations, their members and OAuth applications"),
        Area("Organization application tokens", "an organization's applications' OAuth tokens"),
        Area("Teams", "an organization's teams"),
        Area("The current user", "the signed-in user's own account"),
        Area("Usage logs", "an organization's or a repository's actions"),
        Area("Billing", "plans, subscriptions and invoices"),
        Area("Registry capabilities", "what this registry supports"),
        Area("Discovery", "the API's own description (Swagger)", "https://quay.io/api/v1/discovery"),
        Area("Errors", "the API's error details"),
        Area("Global messages", "messages to every user"),
        Area("Repository tokens", "repository access tokens (deprecated)"),
        Area("User files", "files uploaded for builds"),
    ),
    calls=(
        Call("GET /api/v1/find/repositories", "public repositories whose name or description holds a word (conductRepoSearch)",
             "Search", used="Find an image: Quay.io's results"),
        Call("GET /api/v1/repository/{repository}/tag/", "a repository's tags, active ones (listRepoTags)", "Tags",
             used="Details: a Quay image's newest tags"),
        Call("GET /api/v1/repository", "repositories listed (listRepos)", "Repositories"),
        Call("GET /api/v1/repository/{repository}", "one repository (getRepo)", "Repositories"),
        Call("GET /api/v1/repository/{repository}/manifest/{manifestref}/security", "a manifest's vulnerabilities "
             "(getRepoManifestSecurity)", "Security scans"),
        Call("PUT /api/v1/repository/{repository}/tag/{tag}", "a tag moved to another image (changeTag)", "Tags", writes=True),
        Call("POST /api/v1/repository", "a repository made (createRepo)", "Repositories", writes=True),
    ),
    verified=VERIFIED)

ARTIFACT_HUB = Api(
    name=ARTIFACTHUB, maker="Artifact Hub (a CNCF project)", kind="rest",
    about=("Artifact Hub's API: the cloud-native packages its repositories publish (Helm charts, operators, policies, "
           "container images and more), with their versions, security reports and changelogs, and users' stars, "
           "subscriptions and webhooks. The plugin searches its container images and reads one image's detail."),
    base="https://artifacthub.io/api/v1", version="1.23.0 (its OpenAPI)",
    auth="none to search and read; an API key (X-API-KEY-ID and X-API-KEY-SECRET headers) or a session for a user's own",
    limits=("429 when too many requests come in a while (no number published); the plugin asks at most once a second and "
            "leaves it alone when it answers 403 or 429"),
    costs="",
    links=(
        Link("Artifact Hub API", "https://artifacthub.io/docs/api/", "reference"),
        Link("Artifact Hub documentation", "https://artifacthub.io/docs/", "docs"),
        Link("Container images repositories", "https://artifacthub.io/docs/topics/repositories/container-images/", "guide"),
        Link("FAQ", "https://artifacthub.io/docs/topics/faq/", "guide"),
        Link("OpenAPI", "https://artifacthub.io/docs/api/openapi.yaml", "spec"),
        Link("artifacthub/hub", "https://github.com/artifacthub/hub", "source"),
    ),
    areas=(
        Area("Packages", "packages searched and read, their versions, security reports, values, templates and changelogs",
             covered="Find an image: container images (kind 12); Details: one image's description, README and scan summary"),
        Area("Repositories", "the repositories that publish packages", "https://artifacthub.io/docs/topics/repositories/"),
        Area("Users", "registration, sign-in, profiles and passwords"),
        Area("Organizations", "organizations and their members"),
        Area("Subscriptions", "a user's subscriptions to a package's new releases"),
        Area("Webhooks", "calls made when a package changes"),
        Area("Availability checks", "whether a name is free"),
        Area("Stats", "the hub's figures"),
        Area("Integrations", "Harbor replication, the Helm exporter, Nova"),
    ),
    calls=(
        Call("GET /packages/search", "packages for words, of a kind (12: container images)", "Packages",
             used="Find an image: Artifact Hub's results"),
        Call("GET /packages/container/{repoName}/{packageName}", "a container image's package", "Packages",
             used="Details: an Artifact Hub image's description, README and scan summary"),
        Call("GET /packages/{packageID}/{version}/security-report", "a version's vulnerability report", "Packages"),
        Call("GET /packages/{repoKindParam}/{repoName}/{packageName}/changelog.md", "a package's changelog", "Packages"),
        Call("GET /repositories/search", "repositories searched", "Repositories"),
        Call("GET /packages/stats", "how many packages and releases there are", "Packages"),
        Call("PUT /packages/{packageID}/stars", "a package starred (signed in)", "Packages", writes=True),
        Call("POST /subscriptions", "a subscription to a package's releases (signed in)", "Subscriptions", writes=True),
    ),
    verified=VERIFIED)

OCI_DISTRIBUTION = Api(
    name=OCI, maker="Open Container Initiative", kind="rest",
    about=("The HTTP API every container registry speaks (Docker Hub's registry, GHCR, Quay, a project's own): an image's "
           "manifests and blobs pulled and pushed, its tags listed, its referrers found, content deleted; public images "
           "read with an anonymous token when the registry asks for one. The plugin lists an image's tags on its own "
           "registry and reads Docker Hub's pull allowance the way Docker documents it (a HEAD, which spends no pull)."),
    base="https://<registry>/v2/ (registry-1.docker.io, ghcr.io, quay.io …)",
    version="Distribution Specification v1.1.1",
    auth=("anonymous for public images: a 401's WWW-Authenticate Bearer challenge names a token service, asked for a "
          "pull-scoped token (the token authentication specification)"),
    limits=("each registry's own: Docker Hub counts a manifest's GET as a pull (100 per 6 hours per address without an "
            "account), never a HEAD; the others publish theirs"),
    costs="",
    links=(
        Link("OCI Distribution Specification", _OCI_SPEC, "docs"),
        Link("HTTP API V2 (CNCF Distribution)", "https://distribution.github.io/distribution/spec/api/", "reference"),
        Link("Token authentication specification", "https://distribution.github.io/distribution/spec/auth/token/", "auth"),
        Link("Docker Hub pull usage and limits", "https://docs.docker.com/docker-hub/usage/pulls/", "limits"),
        Link("Its releases", "https://github.com/opencontainers/distribution-spec/releases", "changelog"),
        Link("opencontainers/distribution-spec", "https://github.com/opencontainers/distribution-spec", "source"),
    ),
    areas=(
        Area("Pull", "manifests and blobs fetched, or checked with a HEAD", _OCI_SPEC + "#pull",
             covered="Docker Hub's anonymous pulls left, read with a HEAD of a manifest (no pull spent)"),
        Area("Content discovery", "an image's tags listed; its referrers (signatures, SBOMs) found", _OCI_SPEC + "#content-discovery",
             covered="Details: the tags of an image on its own registry (GHCR, a project's own)"),
        Area("Token authentication", "a bearer token for a scope, from the realm a 401 names",
             "https://distribution.github.io/distribution/spec/auth/token/",
             covered="an anonymous pull token when a registry asks for one"),
        Area("Push", "blobs uploaded (whole, in chunks, mounted from another repository) and manifests put", _OCI_SPEC + "#push"),
        Area("Content management", "tags, manifests and blobs deleted", _OCI_SPEC + "#content-management"),
        Area("Determining support", "whether a registry speaks the API (GET /v2/)", _OCI_SPEC + "#determining-support"),
    ),
    calls=(
        Call("GET /v2/{name}/tags/list", "an image's tags (n at most)", "Content discovery",
             used="Details: an image's tags on its own registry", docs=_OCI_SPEC + "#listing-tags"),
        Call("GET {realm}?service={service}&scope=repository:{name}:pull", "an anonymous token for one image's pull",
             "Token authentication", used="a token when a registry answers 401; Docker Hub's allowance check",
             docs="https://distribution.github.io/distribution/spec/auth/token/"),
        Call("HEAD /v2/{name}/manifests/{reference}", "whether a manifest is there, its headers alone", "Pull",
             used="Docker Hub's anonymous pulls left (ratelimitpreview/test: a HEAD spends no pull)",
             docs=_OCI_SPEC + "#pulling-manifests"),
        Call("GET /v2/", "whether the registry speaks the API", "Determining support", docs=_OCI_SPEC + "#determining-support"),
        Call("GET /v2/{name}/manifests/{reference}", "a manifest fetched (on Docker Hub: a pull counted)", "Pull",
             docs=_OCI_SPEC + "#pulling-manifests"),
        Call("GET /v2/{name}/blobs/{digest}", "a layer or config fetched", "Pull", docs=_OCI_SPEC + "#pulling-blobs"),
        Call("GET /v2/{name}/referrers/{digest}", "what refers to a manifest (signatures, SBOMs)", "Content discovery",
             docs=_OCI_SPEC + "#listing-referrers"),
        Call("POST /v2/{name}/blobs/uploads/", "a blob's upload begun", "Push", docs=_OCI_SPEC + "#pushing-blobs", writes=True),
        Call("PUT /v2/{name}/manifests/{reference}", "a manifest pushed", "Push", docs=_OCI_SPEC + "#pushing-manifests",
             writes=True),
        Call("DELETE /v2/{name}/manifests/{reference}", "a manifest deleted", "Content management",
             docs=_OCI_SPEC + "#deleting-manifests", writes=True),
    ),
    verified=VERIFIED)

APIS = (DOCKER_CLI, DOCKER_HUB, QUAY_IO, ARTIFACT_HUB, OCI_DISTRIBUTION)
HOSTS = {"hub.docker.com": HUB, "quay.io": QUAY, "artifacthub.io": ARTIFACTHUB}  # every other host: the OCI registry API
