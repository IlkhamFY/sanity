#!/usr/bin/env python3
"""Pull and print runs whose stage matches a role.

Optional. An @mention in the Telegram group is the trigger. This script
does not write a run, commit, or post.

    python3 scripts/watch_runs.py --role verifier --interval 15
    python3 scripts/watch_runs.py --role reader --once --no-pull
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROLES = ("reader", "verifier", "writer")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pull(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "pull", "--ff-only"],
        check=False,
    )


def matching_runs(runs_dir: Path, role: str) -> list[dict]:
    found = []
    if not runs_dir.is_dir():
        return found
    for status_path in sorted(runs_dir.glob("*/status.json")):
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("stage") != role:
            continue
        slug = status_path.parent.name
        found.append(
            {
                "slug": slug,
                "paper": data.get("paper", slug),
                "stage": data.get("stage", ""),
                "owner_bot": data.get("owner_bot", ""),
                "updated_at": data.get("updated_at", ""),
                "commit": data.get("commit", ""),
                "notes": data.get("notes", ""),
            }
        )
    return found


def format_line(row: dict) -> str:
    return (
        f"runs/{row['slug']}  stage={row['stage']}  "
        f"owner_bot={row['owner_bot']}  commit={row['commit']}"
    )


def scan(runs_dir: Path, role: str) -> list[str]:
    return [format_line(row) for row in matching_runs(runs_dir, role)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--interval", type=float, default=15, help="seconds between pulls")
    parser.add_argument("--once", action="store_true", help="scan one time and exit")
    parser.add_argument("--no-pull", action="store_true", help="do not git pull")
    parser.add_argument("--runs", type=Path, default=None, help="runs directory (tests)")
    args = parser.parse_args(argv)
    if args.interval < 0:
        print("watch_runs: interval must be >= 0", file=sys.stderr)
        return 2
    root = repo_root()
    runs_dir = args.runs if args.runs is not None else root / "runs"
    while True:
        if not args.no_pull:
            pull(root)
        lines = scan(runs_dir, args.role)
        if lines:
            print("\n".join(lines), flush=True)
        else:
            print(f"no runs in stage {args.role}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
