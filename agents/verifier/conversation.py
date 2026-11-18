"""Log the Verifier's conversation for a run in conversation.jsonl.

    python conversation.py add  --dir ATTEMPT_DIR --role verifier --kind question --text "..." \
                                [--eq 12] [--sender NAME] [--message-id N] [--reply-to N] [--file PATH ...]
    python conversation.py show --dir ATTEMPT_DIR

One JSON object per line, appended, never rewritten:

    {"time": "2026-11-18T14:02:11+00:00", "role": "verifier", "kind": "question",
     "eq": "12", "sender": "@koni_master_hermes_bot", "message_id": 812, "reply_to": 790,
     "text": "eq (12) is \\simeq with no regime. Does the paper state k H >> 1?",
     "files": [{"name": "equations.json", "sha256": "..."}]}

role:  verifier | reader | human | writer
kind:  question  the Verifier asks (counted against the question limit)
       answer    a reply to a question (text and/or a new equations.json)
       command   a human instruction (stop, rerun, status)
       note      anything else worth keeping, e.g. the start and handoff messages

The log ships in the evidence bundle, so a reader of the bundle can see which
clarifications changed which claims.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROLES = ("verifier", "reader", "human", "writer")
KINDS = ("question", "answer", "command", "note")
LOG = "conversation.jsonl"


class ConversationError(ValueError):
    """Raised for an entry that does not fit the log format."""


def append(attempt_dir: Path, role: str, kind: str, text: str, *, eq: str | None = None,
           sender: str | None = None, message_id: int | None = None, reply_to: int | None = None,
           files: list[Path] | None = None, now: datetime.datetime | None = None) -> dict:
    """Append one entry and return it."""
    if role not in ROLES:
        raise ConversationError(f"role must be one of {', '.join(ROLES)}, not {role!r}")
    if kind not in KINDS:
        raise ConversationError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    if kind == "question" and role != "verifier":
        raise ConversationError("only the verifier asks questions")
    if kind == "question" and not eq:
        raise ConversationError("a question must name the equation it is about (eq)")
    attempt_dir = Path(attempt_dir)
    if not attempt_dir.is_dir():
        raise ConversationError(f"no such attempt folder: {attempt_dir}")
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds")
    entry = {
        "time": stamp,
        "role": role,
        "kind": kind,
        "eq": eq,
        "sender": sender,
        "message_id": message_id,
        "reply_to": reply_to,
        "text": text,
        "files": [
            {"name": Path(f).name, "sha256": hashlib.sha256(Path(f).read_bytes()).hexdigest()}
            for f in (files or [])
        ],
    }
    with (attempt_dir / LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read(attempt_dir: Path) -> list[dict]:
    path = Path(attempt_dir) / LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def questions_asked(attempt_dir: Path) -> int:
    return sum(entry["kind"] == "question" for entry in read(attempt_dir))


def open_questions(attempt_dir: Path) -> list[dict]:
    """Questions with no answer that replies to their message_id (or, without ids, no later answer)."""
    entries = read(attempt_dir)
    answered_ids = {e["reply_to"] for e in entries if e["kind"] == "answer" and e["reply_to"] is not None}
    pending = []
    for index, entry in enumerate(entries):
        if entry["kind"] != "question":
            continue
        if entry["message_id"] is not None:
            if entry["message_id"] not in answered_ids:
                pending.append(entry)
        elif not any(e["kind"] == "answer" for e in entries[index + 1:]):
            pending.append(entry)
    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifier conversation log.")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--dir", required=True, type=Path)
    add.add_argument("--role", required=True, choices=ROLES)
    add.add_argument("--kind", required=True, choices=KINDS)
    add.add_argument("--text", required=True)
    add.add_argument("--eq")
    add.add_argument("--sender")
    add.add_argument("--message-id", type=int)
    add.add_argument("--reply-to", type=int)
    add.add_argument("--file", type=Path, action="append", default=[])
    show = sub.add_parser("show")
    show.add_argument("--dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            entry = append(args.dir, args.role, args.kind, args.text, eq=args.eq, sender=args.sender,
                           message_id=args.message_id, reply_to=args.reply_to, files=args.file)
            print(json.dumps(entry, ensure_ascii=False))
        else:
            print(json.dumps({
                "entries": read(args.dir),
                "questions_asked": questions_asked(args.dir),
                "open_questions": open_questions(args.dir),
            }, indent=2, ensure_ascii=False))
    except ConversationError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
