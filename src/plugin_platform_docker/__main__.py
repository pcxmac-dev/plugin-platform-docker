"""`python -m plugin_platform_docker ...`: the plugin from the command line (the platform's page asks the same hooks).
`status` prints the status as the page gets it; `engines` each engine in a line; `containers`, `images`, `volumes` and
`networks` the table of the engine named (the one the page would show unless named); `logs` a container's last lines;
`start`, `stop`, `restart`, `remove`, `pull` and `rmi` change what they say, `--force` accepting what the page asks
again (a running container removed, an image a container was made from removed). An engine in a stopped WSL
distribution is not asked, and not started."""
from __future__ import annotations

import json
import sys

from liminal_libs.docker import DockerError

from . import MACHINE, Refusal

USAGE = ("python -m plugin_platform_docker status | engines | containers|images|volumes|networks [ENGINE] | logs ENGINE NAME [LINES]"
         " | start|stop|restart ENGINE NAME | remove ENGINE NAME [--force] | pull ENGINE IMAGE | rmi ENGINE IMAGE [--force]")
TABLES = {"containers": "Containers", "images": "Images", "volumes": "Volumes", "networks": "Networks"}


def flat(c) -> str:
    """A table's cell as text: its words with what is beneath in brackets; a button is left out."""
    if isinstance(c, dict):
        if "form" in c:
            return ""
        return f"{c.get('text', '')} ({c['sub']})" if c.get("sub") else str(c.get("text", ""))
    return str(c)


def said(answer: dict) -> int:
    print(answer.get("said", ""))
    for line in answer.get("lines") or []:
        print(f"  {line}")
    return 0 if answer.get("ok", True) else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    what, rest = (argv[0], argv[1:]) if argv else ("status", [])
    force = "--force" in rest
    rest = [r for r in rest if r != "--force"]
    try:
        if what == "status" and not rest:
            s = MACHINE.status()
            print(json.dumps(s, indent=1))
            return 0 if s.get("valid") else 1
        if what == "engines" and not rest:
            seen = MACHINE.engines()
            for e in seen:
                print(f"{e.line()}  ({e.instance.where})")
            if not seen:
                print("no Docker engine here")
            return 0 if any(e.answering for e in seen) else 1
        if what in TABLES and len(rest) <= 1:
            if rest:
                MACHINE.choose_engine(rest[0])
            s = MACHINE.status()
            table = next((t for t in s["tables"] if t["title"] == TABLES[what]), None)
            if table is None:
                print(next((t.get("empty") for t in s["tables"] if t["title"] == "Containers"), None) or s["why"], file=sys.stderr)
                return 1
            print(f"{table['title']} {table.get('note', '')}".strip())
            for row in table["rows"]:
                print("  " + "  ".join(x for x in (flat(c) for c in row) if x))
            if not table["rows"]:
                print(f"  {table.get('empty', 'none')}")
            return 0
        if what == "logs" and len(rest) in (2, 3):
            return said(MACHINE.logs(*rest))
        if what in ("start", "stop", "restart") and len(rest) == 2:
            return said(MACHINE.container(rest[0], rest[1], what))
        if what == "remove" and len(rest) == 2:
            return said(MACHINE.remove_container(rest[0], rest[1], force))
        if what == "pull" and len(rest) == 2:
            return said(MACHINE.pull(rest[0], rest[1]))
        if what == "rmi" and len(rest) == 2:
            return said(MACHINE.remove_image(rest[0], rest[1], force))
    except Refusal as e:
        print(f"refused: {e}" + (" (--force does it anyway)" if e.accept == "force" else ""), file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except DockerError as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
