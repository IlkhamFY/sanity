"""Receive equations.json into the Verifier's scratch folder, and report run state.

    python intake.py receive --slug SLUG --file PATH [--sha256 HEX] [--new-attempt] [--scratch DIR]
    python intake.py status  --slug SLUG [--scratch DIR]

Layout under the scratch folder (default: the current directory, which is the
Verifier's Hermes working folder):

    <slug>/<attempt>/
      equations.v1.json, equations.v2.json, ...   every version received, never edited
      equations.json                              copy of the latest version (what checks use)
      conversation.jsonl                          see conversation.py
      verify/PLAN.md, verify/checks/, ...         see verify_run.py
      <slug>-<attempt>.tar.gz                     see bundle.py

``receive`` checks the sha256 (if given), validates the file against the
equations schema (parsing every sympy field safely, via claims.py), checks
that its slug matches, and stores it as the next version of the current
attempt. A file identical to the latest version is not stored twice.
A new attempt n+1 starts when there is none yet, when ``--new-attempt`` is
given (a human asked for a re-run), or when a different file arrives after the
current attempt already has verdicts.

Chat sessions do not share memory, so the state of a run lives here, on disk.
``status`` prints it as JSON: attempts, versions, whether verdicts and a
bundle exist, and whether an identical equations.json was already verified.

Both commands print JSON. Exit 1 if the file is rejected, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from claims import ClaimError, load_claims

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION = re.compile(r"^equations\.v(\d+)\.json$")


class IntakeError(ValueError):
    """Raised when a received file is rejected."""


@dataclass(frozen=True)
class Received:
    slug: str
    attempt: int
    version: int
    sha256: str
    equations: int
    path: str
    duplicate: bool
    already_verified_in: int | None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_slug(slug: str) -> None:
    if not SLUG.match(slug):
        raise IntakeError(f"invalid slug {slug!r}: use lowercase letters, digits and hyphens")


def attempts(scratch: Path, slug: str) -> list[int]:
    folder = Path(scratch) / slug
    if not folder.is_dir():
        return []
    return sorted(int(p.name) for p in folder.iterdir() if p.is_dir() and p.name.isdigit())


def versions(attempt_dir: Path) -> list[int]:
    found = []
    for path in Path(attempt_dir).glob("equations.v*.json"):
        match = VERSION.match(path.name)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


def start_attempt(scratch: Path, slug: str) -> Path:
    """Create attempt n+1 with an empty verify/checks folder."""
    check_slug(slug)
    number = (attempts(scratch, slug) or [0])[-1] + 1
    folder = Path(scratch) / slug / str(number)
    (folder / "verify" / "checks").mkdir(parents=True)
    return folder


def verified_with(scratch: Path, slug: str, sha256: str) -> int | None:
    """Latest attempt whose equations.json has this hash and has verdicts."""
    for number in reversed(attempts(scratch, slug)):
        folder = Path(scratch) / slug / str(number)
        current = folder / "equations.json"
        if (folder / "verify" / "verdicts.json").is_file() and current.is_file():
            if sha256_file(current) == sha256:
                return number
    return None


def receive(scratch: Path, slug: str, source: Path, expected_sha256: str | None = None,
            new_attempt: bool = False) -> Received:
    """Validate ``source`` and store it as the next equations version."""
    check_slug(slug)
    source = Path(source)
    if not source.is_file():
        raise IntakeError(f"no such file: {source}")
    sha = sha256_file(source)
    if expected_sha256 and sha != expected_sha256.lower():
        raise IntakeError(f"sha256 mismatch: header says {expected_sha256}, file is {sha}")
    try:
        claims = load_claims(source)
    except ClaimError as exc:
        raise IntakeError(str(exc)) from None
    data = json.loads(source.read_text(encoding="utf-8"))
    if data["slug"] != slug:
        raise IntakeError(f"equations.json has slug {data['slug']!r}, message says {slug!r}")

    already = verified_with(scratch, slug, sha)
    existing = attempts(scratch, slug)
    current = Path(scratch) / slug / str(existing[-1]) if existing else None
    finished = current is not None and (current / "verify" / "verdicts.json").is_file()
    if new_attempt or current is None:
        folder = start_attempt(scratch, slug)
    elif finished:
        # Same file as the finished attempt: report it, do not start over.
        if (current / "equations.json").is_file() and sha256_file(current / "equations.json") == sha:
            latest = versions(current)[-1]
            return Received(slug, int(current.name), latest, sha, len(claims),
                            str(current / f"equations.v{latest}.json"), True, already)
        folder = start_attempt(scratch, slug)
    else:
        folder = current
    have = versions(folder)
    if have:
        latest = folder / f"equations.v{have[-1]}.json"
        if sha256_file(latest) == sha:
            return Received(slug, int(folder.name), have[-1], sha, len(claims), str(latest), True, already)
    number = (have or [0])[-1] + 1
    stored = folder / f"equations.v{number}.json"
    shutil.copyfile(source, stored)
    shutil.copyfile(source, folder / "equations.json")
    return Received(slug, int(folder.name), number, sha, len(claims), str(stored), False, already)


def status(scratch: Path, slug: str) -> dict:
    """Everything a fresh session needs to know about a run."""
    check_slug(slug)
    result = {"slug": slug, "attempts": []}
    for number in attempts(scratch, slug):
        folder = Path(scratch) / slug / str(number)
        current = folder / "equations.json"
        bundles = sorted(p.name for p in folder.glob(f"{slug}-{number}.tar.gz"))
        log = folder / "conversation.jsonl"
        entries = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        result["attempts"].append(
            {
                "attempt": number,
                "path": str(folder),
                "versions": versions(folder),
                "equations_sha256": sha256_file(current) if current.is_file() else None,
                "plan": (folder / "verify" / "PLAN.md").is_file(),
                "checks": len(list((folder / "verify" / "checks").glob("*.py"))),
                "verdicts": (folder / "verify" / "verdicts.json").is_file(),
                "bundle": bundles[0] if bundles else None,
                "conversation_entries": len(entries),
            }
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifier intake and run state.")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("receive", help="store a received equations.json")
    rec.add_argument("--slug", required=True)
    rec.add_argument("--file", required=True, type=Path)
    rec.add_argument("--sha256")
    rec.add_argument("--new-attempt", action="store_true")
    rec.add_argument("--scratch", type=Path, default=Path("."))
    st = sub.add_parser("status", help="print the state of a run")
    st.add_argument("--slug", required=True)
    st.add_argument("--scratch", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        if args.command == "receive":
            result = asdict(receive(args.scratch, args.slug, args.file, args.sha256, args.new_attempt))
        else:
            result = status(args.scratch, args.slug)
    except IntakeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
