"""Telegram publisher. The only process that commits this repo.

    SANITY_PUBLISHER_BOT_TOKEN=... SANITY_DEPLOY_KEY=... python3 scripts/publisher.py
    # or put the token in ~/.sanity/publisher_token (SANITY_PUBLISHER_BOT_TOKEN_FILE)
    python3 scripts/publisher.py --dry-run

It reads the group with getUpdates and its own bot token. It acts on two headers:

    sanity run=<slug> to=publisher stage=publish
    sanity run=<slug> to=publisher stage=event

stage=publish carries one zip (equations.json, verdicts.json, report.html,
and the check scripts). meta.json is the Reader's record, carried through the
Verifier. If the zip has none, the daemon builds it. It validates the bundle,
runs publish_run.py, and commits
as Ilkham Yabbarov <ilkhamfy@gmail.com> with message "site". The push goes to
branch data and is never a force push. The same zip twice does not make a second
commit. stage=event appends one activity line.

Every reply to a publish goes back as a *reply* to that message, with a header the
Writer's wake word catches (it cannot wait for an answer; the reply starts its turn):

    sanity run=<slug> to=writer status=published url=<page url>
    sanity run=<slug> to=writer status=error        (the reason on the next line)

An event error is for people: ``sanity run=<slug> status=error`` (no ``to=``).

LLM bots do not hold the token or the deploy key. See docs/setup-publisher.md.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fetch_paper import FetchError, build_file_meta, build_meta, classify, remote_entry, subject_errors
from guard import (
    EQUATIONS_SCHEMA,
    META_SCHEMA,
    VERDICTS_SCHEMA,
    _schema_errors,
    _script_errors,
    equation_names,
    external_script_errors,
    failing_claims,
    report_section_text,
    report_url_errors,
    summary_errors,
    validate_repo,
)
from publish_run import REPO, ROLES, find_verdicts, load_json, publish, record_event

SITE = "https://ilkhamfy.github.io/sanity"
AUTHOR = "Ilkham Yabbarov"
EMAIL = "ilkhamfy@gmail.com"
PUSH = ["git", "push", "origin", "HEAD:data"]
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GAP = 1.0
BUNDLE = ("equations.json", "report.html")
PAPER_SUFFIXES = {".pdf", ".tex", ".md", ".markdown"}
NOT_A_PAPER = {"report.md", "telegram.md", "plan.md", "results.md", "readme.md"}
NULLABLE = {"arxiv_id", "version", "primary_category", "doi", "journal_ref", "fetched_at", "example"}
_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$", re.I)
_DOI_ID = re.compile(r"^10\.\d{4,9}/\S+$")
MAX_DOCUMENT = 20 * 1024 * 1024
ZIP_MIME = {"application/zip", "application/x-zip-compressed", "application/x-zip"}
HEADER_HINT = (
    "header: sanity run=<slug> to=publisher stage=publish (one zip) "
    "or stage=event (one line starting Reader:, Verifier:, or Writer:)"
)
_MENTION = re.compile(r"^(?:@\S+\s+)+")
_TO_PUBLISHER = re.compile(r"\bto=publisher\b")


class PublisherError(RuntimeError):
    pass


def parse_header(text: str) -> dict | None:
    """The first line, if it is a publisher header. Later lines are the body.

    A leading @mention, such as @SanityPublisherBot, is ignored.
    """
    line = (text or "").splitlines()[0].strip() if text else ""
    line = _MENTION.sub("", line)
    if not line.startswith("sanity "):
        return None
    fields = {}
    for part in line.split()[1:]:
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        fields[key] = value
    if fields.get("to") != "publisher":
        return None
    if fields.get("stage") not in {"publish", "event"}:
        return None
    if not SLUG.fullmatch(fields.get("run") or ""):
        return None
    if "arxiv" in fields and not _ARXIV_ID.fullmatch(fields["arxiv"]):
        return None
    if "doi" in fields and not _DOI_ID.fullmatch(fields["doi"]):
        return None
    return fields


def mentions_publisher(text: str) -> bool:
    return bool(_TO_PUBLISHER.search(text or ""))


def zip_document(document: dict) -> bool:
    name = (document.get("file_name") or "").lower()
    mime = (document.get("mime_type") or "").lower()
    if name.endswith(".zip"):
        return True
    return mime in ZIP_MIME


def attachment_error(document: dict, header: dict | None) -> str | None:
    """Reject a document before it is downloaded. None means it may be fetched."""
    if not document:
        return None
    size = document.get("file_size")
    if isinstance(size, int) and size > MAX_DOCUMENT:
        return "attachment is over 20 MB"
    if header and header.get("stage") == "publish" and (document.get("file_name") or document.get("mime_type")):
        if not zip_document(document):
            return "publish attachment must be a .zip"
    return None


def answer(header: dict, body: str, *, ok: bool) -> str:
    """The reply text: a header line, then the human-readable body.

    A publish result goes to the Writer (``to=writer``), so its wake word catches it.
    An event error has no ``to=``: it is for people, and no bot wakes for it.
    """
    run = header.get("run", "")
    if header.get("stage") == "publish":
        status = "published" if ok and "published" in body else "error"
        url = body.rsplit("-> ", 1)[1].strip() if status == "published" and "-> " in body else ""
        line = f"sanity run={run} to=writer status={status}" + (f" url={url}" if url else "")
    else:
        line = f"sanity run={run} status={'ok' if ok else 'error'}"
    return f"{line}\n{body}"


def activity_role(header: dict, line: str) -> str | None:
    named = (header.get("role") or "").lower()
    if named in ROLES:
        return named
    if not line:
        return None
    first = line.split(None, 1)[0].lower().rstrip(".:")
    if first in ROLES:
        return first
    return None


def safe_unzip(blob: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise PublisherError(f"publish attachment is not a zip: {exc}") from None
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise PublisherError(f"unsafe path in zip: {info.filename}")
            target = dest.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def _blank(value) -> bool:
    return value is None or value == "" or value == []


def _needs(meta: dict, key: str) -> bool:
    """A field the zip left out. Explicit nulls (no arXiv id, no DOI) stay null."""
    if key not in meta:
        return True
    if key in NULLABLE:
        return False
    return _blank(meta.get(key))


def _now_stamp(now) -> str:
    when = now or datetime.now(timezone.utc)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_paper(run: Path) -> Path | None:
    """A pdf, tex, or md file in the bundle. source/ and paper.* come first."""
    found = [
        path for path in run.rglob("*")
        if path.is_file()
        and path.suffix.lower() in PAPER_SUFFIXES
        and path.name.lower() not in NOT_A_PAPER
        and "__pycache__" not in path.parts
        and "verify" not in path.parts
    ]
    if not found:
        return None

    def rank(path: Path) -> tuple:
        rel = path.relative_to(run).as_posix()
        return (0 if rel.startswith("source/") else 1, 0 if path.name.lower().startswith("paper.") else 1, rel)

    return sorted(found, key=rank)[0]


def _html_section(html: str, word: str) -> str:
    match = re.search(
        rf"<h[1-3][^>]*>[^<]*{word}[^<]*</h[1-3]>(.*?)(?=<h[1-3][\s>]|$)",
        html or "",
        re.I | re.S,
    )
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", text).strip()


def keep_fails_only(text: str, fails: set[str]) -> str:
    """Drop sentences that name an equation whose verdict is not FAILS."""
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        if not sentence:
            continue
        if equation_names(sentence) <= fails:
            kept.append(sentence)
    return " ".join(kept).strip()


def _fresh_meta(run: Path, header: dict, *, opener, sleeper, stamp: str) -> dict:
    """Metadata when the zip did not bring a complete record. No bot has to pass it."""
    slug = header["run"]
    spec = header.get("arxiv") or header.get("doi")
    if spec:
        entry = remote_entry(spec, opener=opener, sleeper=sleeper)
        meta = build_meta(entry, stamp)
        meta["slug"] = slug
        return meta
    paper = find_paper(run)
    if paper is not None:
        return build_file_meta(paper, slug, stamp)
    equations = load_json(run / "equations.json") if (run / "equations.json").is_file() else {}
    report = (run / "REPORT.md").read_text(encoding="utf-8") if (run / "REPORT.md").is_file() else ""
    title = equations.get("title") if isinstance(equations, dict) else None
    if not title:
        heading = re.search(r"^#\s+(.+)$", report, re.M)
        title = heading.group(1).strip() if heading else None
    return {
        "title": title or slug,
        "authors": ["unknown"],
        "abstract": "",
        "arxiv_id": None,
        "version": None,
        "primary_category": None,
        "doi": None,
        "journal_ref": None,
        "fetched_at": stamp,
        "slug": slug,
        "subject": "unknown",
        "example": True,
        "source": "file",
    }


def ensure_meta(run: Path, header: dict, *, opener=None, sleeper=time.sleep, now=None) -> dict:
    """Use the zip's meta.json when it is there. Build one only when it is missing or incomplete."""
    path = run / "meta.json"
    meta = load_json(path) if path.is_file() else {}
    if not isinstance(meta, dict):
        meta = {}
    stamp = _now_stamp(now)
    bibliographic = (
        "title", "authors", "abstract", "arxiv_id", "version", "primary_category",
        "doi", "journal_ref", "fetched_at", "slug", "subject", "example", "source",
    )
    if any(_needs(meta, key) for key in bibliographic):
        fresh = _fresh_meta(run, header, opener=opener, sleeper=sleeper, stamp=stamp)
        for key in bibliographic:
            if _needs(meta, key):
                meta[key] = fresh.get(key)
    if _blank(meta.get("slug")):
        meta["slug"] = header["run"]
    verdicts_path = find_verdicts(run)
    fails = failing_claims(load_json(verdicts_path)) if verdicts_path is not None else set()
    html = (run / "report.html").read_text(encoding="utf-8") if (run / "report.html").is_file() else ""
    telegram = (run / "telegram.md").read_text(encoding="utf-8") if (run / "telegram.md").is_file() else ""
    summary = _html_section(html, "summary") or telegram
    catch = _html_section(html, "catch")
    if _blank(meta.get("summary")) and summary:
        meta["summary"] = keep_fails_only(summary, fails)
    elif meta.get("summary"):
        meta["summary"] = keep_fails_only(str(meta["summary"]), fails)
    if _blank(meta.get("catch")) and catch:
        meta["catch"] = keep_fails_only(catch, fails)
    elif meta.get("catch"):
        meta["catch"] = keep_fails_only(str(meta["catch"]), fails)
    for key in ("summary", "catch"):
        if key in meta and not str(meta[key]).strip():
            del meta[key]
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def bundle_missing(run: Path) -> list[str]:
    missing = [name for name in BUNDLE if not (run / name).is_file()]
    if find_verdicts(run) is None:
        missing.append("verdicts.json")
    return missing


def digest(run: Path) -> str:
    hasher = hashlib.sha256()
    files = [path for path in run.rglob("*") if path.is_file() and path.name != "publish-sha.txt"]
    for path in sorted(files, key=lambda item: item.relative_to(run).as_posix()):
        hasher.update(path.relative_to(run).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def bundle_problems(run: Path) -> list[str]:
    missing = bundle_missing(run)
    if missing:
        return ["publish bundle is missing " + ", ".join(missing)]
    errors = []
    try:
        meta = load_json(run / "meta.json")
        equations = load_json(run / "equations.json")
        verdicts = load_json(find_verdicts(run))
    except json.JSONDecodeError as exc:
        return [f"bundle JSON is unreadable: {exc}"]
    errors.extend(_schema_errors(equations, EQUATIONS_SCHEMA, "equations.json"))
    errors.extend(_schema_errors(verdicts, VERDICTS_SCHEMA, "verdicts.json"))
    errors.extend(_schema_errors(meta, META_SCHEMA, "meta.json"))
    errors.extend(_script_errors(run, verdicts))
    for problem in subject_errors(meta):
        errors.append(f"meta.json {problem}")
    html = (run / "report.html").read_text(encoding="utf-8")
    errors.extend(report_url_errors(html, "report.html"))
    errors.extend(external_script_errors(html, "report.html"))
    section = report_section_text(html)
    fails = failing_claims(verdicts)
    if not section.strip():
        errors.append("report.html has no summary, judgement, or catch section")
    errors.extend(summary_errors(section, fails, "report.html summary/catch"))
    errors.extend(summary_errors(str(meta.get("summary") or ""), fails, "meta.json summary"))
    errors.extend(summary_errors(str(meta.get("catch") or ""), fails, "meta.json catch"))
    if (run / "telegram.md").is_file():
        errors.extend(summary_errors((run / "telegram.md").read_text(encoding="utf-8"), fails, "telegram.md"))
    return errors


def page_url(slug: str, site: str) -> str:
    return f"{site.rstrip('/')}/papers.html?paper={slug}"


def git_env(deploy_key: str | None) -> dict:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": AUTHOR,
        "GIT_AUTHOR_EMAIL": EMAIL,
        "GIT_COMMITTER_NAME": AUTHOR,
        "GIT_COMMITTER_EMAIL": EMAIL,
    })
    if deploy_key:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {deploy_key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
        )
    return env


def _run(repo: Path, args: list[str], env: dict, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=repo, env=env, text=True, capture_output=True, check=check)


def _ref(repo: Path, name: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", name], cwd=repo, capture_output=True).returncode == 0


def prepare_data_branch(repo: Path, env: dict, *, fetch: bool) -> None:
    """Check out data. Fast-forward it. Merge main in. Never force."""
    dirty = _run(repo, ["git", "status", "--porcelain"], env, check=False)
    if dirty.stdout.strip():
        raise PublisherError("working tree is dirty; the publisher clone must be clean")
    if fetch:
        fetched = _run(repo, ["git", "fetch", "origin"], env, check=False)
        if fetched.returncode != 0:
            raise PublisherError(fetched.stderr.strip() or "git fetch failed")
    if not _ref(repo, "refs/heads/data"):
        _run(repo, ["git", "checkout", "-b", "data"], env)
    else:
        _run(repo, ["git", "checkout", "data"], env)
    if _ref(repo, "refs/remotes/origin/data"):
        ahead = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "origin/data", "HEAD"],
            cwd=repo, capture_output=True,
        ).returncode == 0
        behind = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "HEAD", "origin/data"],
            cwd=repo, capture_output=True,
        ).returncode == 0
        if not ahead and behind:
            merged = _run(repo, ["git", "merge", "--ff-only", "origin/data"], env, check=False)
            if merged.returncode != 0:
                raise PublisherError(merged.stderr.strip() or "could not fast-forward data")
        elif not ahead and not behind:
            raise PublisherError("branch data has diverged; refusing to force-push")
    if _ref(repo, "refs/remotes/origin/main"):
        merged = _run(repo, ["git", "merge", "--no-edit", "-m", "site", "origin/main"], env, check=False)
        if merged.returncode != 0:
            _run(repo, ["git", "merge", "--abort"], env, check=False)
            raise PublisherError(merged.stderr.strip() or "could not merge origin/main into data")


def commit_site(repo: Path, paths: list[str], env: dict, *, push: bool) -> str:
    """Commit path changes. Return 'committed', 'unchanged', or raise."""
    _run(repo, ["git", "add", "--", *paths], env)
    diff = _run(repo, ["git", "diff", "--cached", "--quiet"], env, check=False)
    if diff.returncode == 0:
        return "unchanged"
    committed = _run(
        repo,
        ["git", "-c", f"user.name={AUTHOR}", "-c", f"user.email={EMAIL}", "-c", "commit.gpgsign=false", "commit", "-m", "site"],
        env,
        check=False,
    )
    if committed.returncode != 0:
        raise PublisherError(committed.stderr.strip() or "git commit failed")
    if push:
        pushed = _run(repo, PUSH, env, check=False)
        if pushed.returncode != 0:
            raise PublisherError(pushed.stderr.strip() or "git push failed")
    return "committed"


def rollback(repo: Path, slug: str, env: dict) -> None:
    _run(repo, ["git", "checkout", "--", "site/public/data/papers.json", "site/public/data/activity.json", f"runs/{slug}"], env, check=False)
    _run(repo, ["git", "clean", "-fd", "--", f"runs/{slug}", f"site/public/data/{slug}"], env, check=False)


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("publish-sha.txt"))


class Publisher:
    def __init__(self, repo: Path, *, site: str = SITE, deploy_key: str | None = None, dry_run: bool = False, fetch: bool = True, push: bool = True, opener=None, sleeper=time.sleep, clock=None):
        self.repo = repo
        self.site = site
        self.deploy_key = deploy_key
        self.dry_run = dry_run
        self.fetch = fetch
        self.push = push and not dry_run and bool(deploy_key)
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock
        self.seen: set[str] = set()
        self.queue: list[tuple[int, str, int | None]] = []
        self.last_send = -1e9
        self.pending: dict[str, dict] = {}

    def note_seen(self, chat_id: int, message_id: int) -> bool:
        """Return True if this message was already handled."""
        key = f"{chat_id}:{message_id}"
        if key in self.seen:
            return True
        self.seen.add(key)
        if len(self.seen) > 4000:
            self.seen = set(list(self.seen)[-2000:])
        return False

    def enqueue(self, chat_id: int, text: str, now: float, reply_to: int | None = None) -> list[tuple]:
        self.queue.append((chat_id, text, reply_to))
        return self.drain(now)

    def drain(self, now: float) -> list[tuple[int, str, int | None]]:
        sent = []
        while self.queue and now - self.last_send >= GAP:
            sent.append(self.queue.pop(0))
            self.last_send = now
        return sent

    def handle(self, message: dict, blobs: dict[str, bytes], now: float) -> list[str]:
        """Handle one Telegram message. `blobs` maps file_id to bytes for tests."""
        chat_id = int((message.get("chat") or {}).get("id") or 0)
        message_id = int(message.get("message_id") or 0)
        if message_id and self.note_seen(chat_id, message_id):
            return self.drain(now)
        text = message.get("text") or message.get("caption") or ""
        header = parse_header(text)
        if header is None:
            if mentions_publisher(text):
                return self.enqueue(chat_id, HEADER_HINT, now)
            return self.drain(now)
        document = message.get("document") or {}
        reply_to = message_id or None
        problem = attachment_error(document, header)
        if problem:
            return self.enqueue(chat_id, answer(header, problem, ok=False), now, reply_to)
        try:
            if header["stage"] == "event":
                reply = self._event(header, text, chat_id)
                ok = True
            else:
                reply = self._collect_publish(header, message, blobs, now)
                ok = True
        except (PublisherError, SystemExit) as exc:
            reply, ok = str(exc), False
        if reply:
            return self.enqueue(chat_id, answer(header, reply, ok=ok), now, reply_to)
        return self.drain(now)

    def _event(self, header: dict, text: str, chat_id: int) -> str | None:
        lines = [line.strip() for line in text.splitlines()[1:] if line.strip()]
        if len(lines) != 1:
            raise PublisherError("stage=event needs one activity line")
        role = activity_role(header, lines[0])
        if role is None:
            raise PublisherError("activity line must start with Reader, Verifier, or Writer")
        if self.dry_run:
            return None
        env = git_env(self.deploy_key)
        prepare_data_branch(self.repo, env, fetch=self.fetch)
        record_event(self.repo / "site" / "public" / "data", header["run"], role, lines[0], "", "")
        commit_site(self.repo, ["site/public/data/activity.json"], env, push=self.push)
        return None

    def _collect_publish(self, header: dict, message: dict, blobs: dict[str, bytes], now: float) -> str | None:
        document = message.get("document") or {}
        file_id = document.get("file_id")
        name = document.get("file_name") or ""
        if not file_id or file_id not in blobs:
            raise PublisherError(
                "stage=publish needs one zip attached as that message's document"
            )
        blob = blobs[file_id]
        if name.lower().endswith(".zip") or blob[:2] == b"PK":
            return self._publish_zip(header, blob)
        group = message.get("media_group_id") or header["run"]
        slot = self.pending.setdefault(group, {"slug": header["run"], "files": {}, "started": now})
        slot["files"][Path(name).name] = blob
        slot["slug"] = header["run"]
        needed = set(BUNDLE) | {"verdicts.json"}
        if needed <= set(slot["files"]):
            folder = Path(self.repo).parent / f".publish-{header['run']}"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            try:
                for filename, data in slot["files"].items():
                    (folder / filename).write_bytes(data)
                self.pending.pop(group, None)
                return self._publish_tree(header, folder)
            finally:
                shutil.rmtree(folder, ignore_errors=True)
        if now - slot["started"] > 8:
            self.pending.pop(group, None)
            raise PublisherError("publish bundle is missing " + ", ".join(sorted(needed - set(slot["files"]))))
        return None

    def _publish_zip(self, header: dict, blob: bytes) -> str:
        slug = header["run"]
        folder = self.repo.parent / f".publish-{slug}"
        if folder.exists():
            shutil.rmtree(folder)
        try:
            safe_unzip(blob, folder)
            unpacked = folder / slug if (folder / slug / "equations.json").is_file() else folder
            return self._publish_tree(header, unpacked)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _publish_tree(self, header: dict, folder: Path) -> str:
        slug = header["run"]
        try:
            meta = ensure_meta(folder, header, opener=self.opener, sleeper=self.sleeper, now=self.clock)
        except FetchError as exc:
            raise PublisherError(str(exc)) from exc
        problems = bundle_problems(folder)
        if problems:
            raise PublisherError("; ".join(problems))
        if meta.get("slug") not in {None, slug}:
            raise PublisherError(f"meta.json slug is {meta.get('slug')}, header says {slug}")
        equations = load_json(folder / "equations.json")
        if equations.get("slug") != slug:
            raise PublisherError(f"equations.json slug is {equations.get('slug')}, header says {slug}")
        url = page_url(slug, self.site)
        if self.dry_run:
            return f"dry-run: published {slug} -> {url}"
        subject, example = classify(meta)
        source = None
        if meta.get("arxiv_id"):
            source = f"https://arxiv.org/abs/{meta['arxiv_id']}{meta.get('version') or ''}"
        elif meta.get("doi"):
            source = f"https://doi.org/{meta['doi']}"
        env = git_env(self.deploy_key)
        prepare_data_branch(self.repo, env, fetch=self.fetch)
        dest = self.repo / "runs" / slug
        stamp = dest / "publish-sha.txt"
        current = digest(folder)
        if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == current:
            return f"published {slug} -> {url}"
        copy_tree(folder, dest)
        try:
            publish(
                dest,
                subject,
                None,
                source,
                example,
                self.repo / "site" / "public" / "data",
                REPO / "site" / "public" / "logos",
                preview=False,
                network=False,
            )
            problems = validate_repo(self.repo)
            if problems:
                raise PublisherError("; ".join(problems))
        except SystemExit as exc:
            rollback(self.repo, slug, env)
            raise PublisherError(str(exc)) from None
        except Exception:
            rollback(self.repo, slug, env)
            raise
        stamp.write_text(current + "\n", encoding="utf-8")
        commit_site(
            self.repo,
            [f"runs/{slug}", "site/public/data"],
            env,
            push=self.push,
        )
        return f"published {slug} -> {url}"


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {"offset": 0, "seen": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, offset: int, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"offset": offset, "seen": sorted(seen)[-2000:]}), encoding="utf-8")


class BotApi:
    def __init__(self, token: str):
        self.token = token

    def call(self, method: str, params: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        request = Request(url, data=urlencode(params).encode(), method="POST")
        with urlopen(request, timeout=40) as response:
            payload = json.loads(response.read().decode())
        if not payload.get("ok"):
            raise PublisherError(payload.get("description") or method)
        return payload

    def updates(self, offset: int) -> list[dict]:
        payload = self.call("getUpdates", {"offset": offset, "timeout": 25})
        return payload.get("result") or []

    def download(self, file_id: str) -> bytes:
        payload = self.call("getFile", {"file_id": file_id})
        path = payload["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{path}"
        with urlopen(url, timeout=60) as response:
            return response.read()

    def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        params = {"chat_id": chat_id, "text": text[:3500]}
        if reply_to:
            params["reply_parameters"] = json.dumps({"message_id": reply_to, "allow_sending_without_reply": True})
        self.call("sendMessage", params)


def read_bot_token() -> str:
    """Env SANITY_PUBLISHER_BOT_TOKEN, or the file at SANITY_PUBLISHER_BOT_TOKEN_FILE.

    The file default is ~/.sanity/publisher_token. Whitespace and a leading BOM are stripped.
    """
    raw = os.environ.get("SANITY_PUBLISHER_BOT_TOKEN")
    if raw is None or not raw.strip("\ufeff").strip():
        path = Path(
            os.environ.get("SANITY_PUBLISHER_BOT_TOKEN_FILE")
            or Path.home() / ".sanity" / "publisher_token"
        )
        if not path.is_file():
            raise SystemExit(
                "SANITY_PUBLISHER_BOT_TOKEN is not set and "
                f"{path} does not exist"
            )
        raw = path.read_text(encoding="utf-8-sig")
    token = raw.strip("\ufeff").strip()
    if not token:
        raise SystemExit("SANITY_PUBLISHER_BOT_TOKEN is empty")
    return token


def serve(repo: Path, *, dry_run: bool) -> None:
    token = read_bot_token()
    key = os.environ.get("SANITY_DEPLOY_KEY") or ""
    if not dry_run and not key:
        raise SystemExit("SANITY_DEPLOY_KEY is not set")
    if key and not Path(key).is_file():
        raise SystemExit(f"SANITY_DEPLOY_KEY is not a file: {key}")
    state_path = Path(os.environ.get("SANITY_PUBLISHER_STATE") or Path.home() / ".sanity" / "publisher-state.json")
    state = load_state(state_path)
    api = BotApi(token)
    publisher = Publisher(
        repo,
        site=os.environ.get("SANITY_SITE_URL") or SITE,
        deploy_key=key or None,
        dry_run=dry_run,
        fetch=True,
        push=not dry_run,
    )
    publisher.seen = set(state.get("seen") or [])
    offset = int(state.get("offset") or 0)
    while True:
        batch = api.updates(offset)
        now = time.time()
        outgoing: list[tuple[int, str, int | None]] = []
        for update in batch:
            offset = max(offset, int(update["update_id"]) + 1)
            message = update.get("message") or update.get("channel_post")
            if not message:
                continue
            document = message.get("document") or {}
            text = message.get("text") or message.get("caption") or ""
            blobs = {}
            file_id = document.get("file_id")
            if file_id and attachment_error(document, parse_header(text)) is None:
                blobs[file_id] = api.download(file_id)
            # handle() dedupes and rate-limits the text; send what it returns, to the same chat.
            outgoing.extend(publisher.handle(message, blobs, now))
            now = publisher.last_send if publisher.last_send > 0 else now
        for chat_id, text, reply_to in outgoing:
            if not dry_run:
                api.send(chat_id, text, reply_to)
            print(text)
        save_state(state_path, offset, publisher.seen)
        if dry_run:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish Sanity bundles from the Telegram group.")
    parser.add_argument("--dry-run", action="store_true", help="Read one batch, validate, do not commit or send")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    serve(args.repo, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
