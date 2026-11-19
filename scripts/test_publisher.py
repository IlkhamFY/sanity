"""Publisher parsing, validation, and idempotent commits. No network."""

import io
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fetch_paper import classify
from publisher import PUSH, Publisher, ensure_meta, parse_header, read_bot_token
from publish_run import REPO
from test_fetch_paper import ATOM

SLUG = "example-oscillator"
HEADER = f"sanity run={SLUG} to=publisher stage=publish"


def _zip_bytes() -> bytes:
    root = REPO / "runs" / SLUG
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(root).as_posix())
        meta = {
            "title": "A spring, missing a half",
            "authors": [],
            "abstract": "",
            "arxiv_id": None,
            "version": None,
            "primary_category": None,
            "doi": None,
            "journal_ref": None,
            "fetched_at": None,
            "slug": SLUG,
            "subject": "Examples",
            "example": True,
        }
        assert classify(meta) == ("Examples", True)
        archive.writestr("meta.json", json.dumps(meta))
        archive.writestr(
            "report.html",
            "<h2>Summary</h2><p>Eq. (3) and Eq. (4) fail.</p>"
            "<h2>The catch</h2><p>Eq. (3) and Eq. (4) fail.</p>",
        )
    return buffer.getvalue()


def _message(message_id: int, blob_name: str = "bundle.zip") -> dict:
    return {
        "message_id": message_id,
        "chat": {"id": -100},
        "caption": HEADER,
        "document": {"file_id": "zip", "file_name": blob_name},
    }


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    data = repo / "site" / "public" / "data"
    data.mkdir(parents=True)
    (data / "papers.json").write_text('{"papers": []}\n', encoding="utf-8")
    (data / "activity.json").write_text('{"events": []}\n', encoding="utf-8")
    (repo / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    return repo


def _texts(replies) -> list[str]:
    """The human-readable body of each reply (the line after its sanity header)."""
    out = []
    for _chat, text, *_reply_to in replies:
        out.append(text.split("\n", 1)[1] if text.startswith("sanity run=") else text)
    return out


def _headers(replies) -> list[str]:
    return [text.split("\n", 1)[0] for _chat, text, *_ in replies]


def test_token_from_env_or_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SANITY_PUBLISHER_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SANITY_PUBLISHER_BOT_TOKEN_FILE", raising=False)
    with pytest.raises(SystemExit):
        read_bot_token()
    path = tmp_path / "publisher_token"
    path.write_bytes(b"\xef\xbb\xbf  123:abc \n")
    monkeypatch.setenv("SANITY_PUBLISHER_BOT_TOKEN_FILE", str(path))
    assert read_bot_token() == "123:abc"
    monkeypatch.setenv("SANITY_PUBLISHER_BOT_TOKEN", "\ufeff  456:def \n")
    assert read_bot_token() == "456:def"


def test_mention_and_a_bad_header_get_a_hint(tmp_path):
    mentioned = parse_header("@SanityPublisherBot sanity run=example-oscillator to=publisher stage=event")
    assert mentioned["stage"] == "event"
    bot = Publisher(tmp_path, dry_run=True, fetch=False, push=False)
    bad = {
        "message_id": 9,
        "chat": {"id": -100},
        "text": "@SanityPublisherBot to=publisher please",
    }
    hint = _texts(bot.handle(bad, {}, now=0))
    assert hint and "stage=publish" in hint[0]
    missing = {
        "message_id": 10,
        "chat": {"id": -100},
        "text": f"sanity run={SLUG} to=publisher stage=publish",
    }
    out = _texts(bot.handle(missing, {}, now=2))
    assert out and "zip" in out[0]


def test_oversized_or_non_zip_is_rejected(tmp_path):
    bot = Publisher(tmp_path, dry_run=True, fetch=False, push=False)
    huge = _message(11)
    huge["document"]["file_size"] = 21 * 1024 * 1024
    over = _texts(bot.handle(huge, {"zip": b"PK"}, now=0))
    assert over and "20 MB" in over[0]
    other = _message(12, "notes.pdf")
    other["document"]["mime_type"] = "application/pdf"
    kind = _texts(bot.handle(other, {"zip": b"%PDF"}, now=2))
    assert kind and "zip" in kind[0]


def test_header_parser_ignores_other_roles():
    assert parse_header("hello") is None
    assert parse_header("sanity run=foo to=writer stage=writer") is None
    parsed = parse_header("sanity run=foo stage=publish to=publisher")
    assert parsed == {"run": "foo", "stage": "publish", "to": "publisher"}
    assert "--force" not in PUSH
    assert PUSH == ["git", "push", "origin", "HEAD:data"]


def test_dry_run_does_not_write(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    bot = Publisher(repo, dry_run=True, fetch=False, push=False)
    out = bot.handle(_message(1), {"zip": _zip_bytes()}, now=0)
    assert _texts(out) == [
        f"dry-run: published {SLUG} -> https://ilkhamfy.github.io/sanity/papers.html?paper={SLUG}"
    ]
    assert not (repo / "runs").exists()


def test_same_message_id_is_handled_once(tmp_path):
    bot = Publisher(tmp_path, dry_run=True, fetch=False, push=False)
    blob = {"zip": _zip_bytes()}
    first = _texts(bot.handle(_message(7), blob, now=0))
    second = _texts(bot.handle(_message(7), blob, now=10))
    assert len(first) == 1
    assert second == []


def test_acks_are_rate_limited(tmp_path):
    bot = Publisher(tmp_path, dry_run=True, fetch=False, push=False)
    blob = {"zip": _zip_bytes()}
    first = _texts(bot.handle(_message(1), blob, now=0))
    second = _texts(bot.handle(_message(2), blob, now=0.2))
    later = _texts(bot.drain(1.2))
    assert len(first) == 1
    assert second == []
    assert len(later) == 1


def test_bad_bundle_is_the_error_and_not_a_commit(tmp_path):
    repo = _repo(tmp_path)
    bot = Publisher(repo, dry_run=False, fetch=False, push=False)
    out = _texts(bot.handle(_message(1), {"zip": b"PK\x03\x04not-a-zip"}, now=0))
    assert out and "published" not in out[0]
    assert "not a zip" in out[0]
    log = subprocess.check_output(["git", "log", "--oneline"], cwd=repo, text=True)
    assert "site" not in log


def test_publish_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    bot = Publisher(repo, dry_run=False, fetch=False, push=False)
    blob = {"zip": _zip_bytes()}
    url = f"https://ilkhamfy.github.io/sanity/papers.html?paper={SLUG}"
    first = _texts(bot.handle(_message(1), blob, now=0))
    assert first == [f"published {SLUG} -> {url}"]
    count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=repo, text=True).strip()
    second = _texts(bot.handle(_message(2), blob, now=5))
    assert second == [f"published {SLUG} -> {url}"]
    again = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=repo, text=True).strip()
    assert again == count
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    assert branch == "data"
    author = subprocess.check_output(["git", "log", "-1", "--format=%an%n%ae%n%s"], cwd=repo, text=True)
    assert author.splitlines() == ["Ilkham Yabbarov", "ilkhamfy@gmail.com", "site"]
    paper = json.loads((repo / "site" / "public" / "data" / "papers.json").read_text(encoding="utf-8"))["papers"][0]
    assert paper["example"] is True
    assert paper["subject"] == "Examples"
    assert paper["counts"]["fails"] == 2


def test_event_line_is_recorded_once(tmp_path):
    repo = _repo(tmp_path)
    bot = Publisher(repo, dry_run=False, fetch=False, push=False)
    message = {
        "message_id": 3,
        "chat": {"id": -100},
        "text": f"sanity run={SLUG} to=publisher stage=event\nReader fetched the note.",
    }
    assert _texts(bot.handle(message, {}, now=0)) == []
    events = json.loads((repo / "site" / "public" / "data" / "activity.json").read_text(encoding="utf-8"))["events"]
    assert events[-1]["role"] == "reader"
    assert events[-1]["event"] == "Reader fetched the note."
    bot.handle(message, {}, now=5)
    events_again = json.loads((repo / "site" / "public" / "data" / "activity.json").read_text(encoding="utf-8"))["events"]
    assert events_again == events


def test_publish_reply_wakes_the_writer_and_replies_to_its_message(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    bot = Publisher(repo, dry_run=True, fetch=False, push=False)
    out = bot.handle(_message(41), {"zip": _zip_bytes()}, now=0)
    url = f"https://ilkhamfy.github.io/sanity/papers.html?paper={SLUG}"
    assert _headers(out) == [f"sanity run={SLUG} to=writer status=published url={url}"]
    assert [reply_to for *_rest, reply_to in out] == [41]
    bad = bot.handle(_message(42), {"zip": b"PK\x03\x04not-a-zip"}, now=10)
    assert _headers(bad) == [f"sanity run={SLUG} to=writer status=error"]
    assert [reply_to for *_rest, reply_to in bad] == [42]


def test_publisher_reply_headers_wake_exactly_the_writer():
    import re
    env = (REPO / "hermes" / "writer" / "env.example").read_text(encoding="utf-8")
    writer = re.compile(re.search(r"^TELEGRAM_MENTION_PATTERNS=(.+)$", env, re.M).group(1), re.I)
    reader_env = (REPO / "hermes" / "reader" / "env.example").read_text(encoding="utf-8")
    reader = re.compile(re.search(r"^TELEGRAM_MENTION_PATTERNS=(.+)$", reader_env, re.M).group(1), re.I)
    for status in ("published url=https://x", "error"):
        line = f"sanity run={SLUG} to=writer status={status}"
        assert writer.search(line) and not reader.search(line)


def test_header_accepts_optional_arxiv_and_doi():
    parsed = parse_header(f"{HEADER} arxiv=1234.56789v2")
    assert parsed["arxiv"] == "1234.56789v2"
    parsed = parse_header(f"{HEADER} doi=10.1000/fixture.1")
    assert parsed["doi"] == "10.1000/fixture.1"
    assert parse_header(f"{HEADER} arxiv=not-an-id") is None
    assert parse_header(HEADER)["run"] == SLUG


def _bare(tmp_path: Path) -> Path:
    folder = tmp_path / "bundle"
    folder.mkdir()
    (folder / "equations.json").write_text(
        json.dumps({"title": "From the equations", "slug": "demo-paper"}) + "\n",
        encoding="utf-8",
    )
    return folder


def _opener(payload: bytes):
    def open_url(url):
        return 200, payload
    return open_url


def test_missing_meta_uses_header_arxiv(tmp_path):
    folder = _bare(tmp_path)
    header = {"run": "demo-paper", "arxiv": "1234.56789v2", "stage": "publish", "to": "publisher"}
    when = datetime(2024, 1, 2, tzinfo=timezone.utc)
    meta = ensure_meta(folder, header, opener=_opener(ATOM.encode()), sleeper=lambda _s: None, now=when)
    assert meta["title"] == "A Fixture Title"
    assert meta["authors"] == ["A. One", "B. Two"]
    assert meta["arxiv_id"] == "1234.56789"
    assert meta["example"] is False
    assert meta["slug"] == "demo-paper"
    assert meta["subject"] == "Astrophysics / General relativity"
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["slug"] == "demo-paper"


def test_missing_meta_uses_paper_file(tmp_path):
    folder = _bare(tmp_path)
    source = folder / "source"
    source.mkdir()
    (source / "paper.tex").write_text(
        "\\title{A pasted note}\n\\author{Ada Lovelace}\n\\begin{abstract}A remark.\n\\end{abstract}\n",
        encoding="utf-8",
    )
    header = {"run": "demo-paper", "stage": "publish", "to": "publisher"}
    when = datetime(2024, 1, 2, tzinfo=timezone.utc)
    meta = ensure_meta(folder, header, opener=_opener(b""), now=when)
    assert meta["title"] == "A pasted note"
    assert meta["authors"] == ["Ada Lovelace"]
    assert meta["example"] is True
    assert meta["source"] == "file"
    assert meta["arxiv_id"] is None


def test_missing_meta_is_minimal(tmp_path):
    folder = _bare(tmp_path)
    (folder / "REPORT.md").write_text("# A heading title\n", encoding="utf-8")
    header = {"run": "demo-paper", "stage": "publish", "to": "publisher"}
    when = datetime(2024, 1, 2, tzinfo=timezone.utc)
    meta = ensure_meta(folder, header, now=when)
    assert meta["title"] == "From the equations"
    assert meta["authors"] == ["unknown"]
    assert meta["example"] is True
    assert meta["source"] == "file"
    assert meta["slug"] == "demo-paper"


def test_present_meta_is_kept(tmp_path):
    folder = _bare(tmp_path)
    original = {
        "title": "Keep me",
        "authors": ["Ada Lovelace"],
        "abstract": "Already here.",
        "arxiv_id": None,
        "version": None,
        "primary_category": None,
        "doi": None,
        "journal_ref": None,
        "fetched_at": None,
        "slug": "demo-paper",
        "subject": "Examples",
        "example": True,
        "source": "file",
    }
    (folder / "meta.json").write_text(json.dumps(original), encoding="utf-8")

    def explode(_url):
        raise AssertionError("complete meta.json must not be fetched")

    header = {"run": "demo-paper", "arxiv": "1234.56789v2", "stage": "publish", "to": "publisher"}
    meta = ensure_meta(folder, header, opener=explode, now=datetime(2024, 1, 2, tzinfo=timezone.utc))
    assert meta["title"] == "Keep me"
    assert meta["authors"] == ["Ada Lovelace"]
    assert meta["arxiv_id"] is None


def test_summary_drops_sentences_that_are_not_fails(tmp_path):
    folder = _bare(tmp_path)
    (folder / "verdicts.json").write_text(
        json.dumps({"claims": [
            {"claim": "1", "verdict": "HOLDS"},
            {"claim": "3", "verdict": "FAILS"},
        ]}),
        encoding="utf-8",
    )
    (folder / "report.html").write_text(
        "<h2>Summary</h2><p>Eq. (1) holds. Eq. (3) fails.</p>"
        "<h2>The catch</h2><p>Eq. (1) is fine. Eq. (3) fails.</p>",
        encoding="utf-8",
    )
    header = {"run": "demo-paper", "stage": "publish", "to": "publisher"}
    meta = ensure_meta(folder, header, now=datetime(2024, 1, 2, tzinfo=timezone.utc))
    assert "Eq. (1)" not in meta["summary"]
    assert "Eq. (3) fails." in meta["summary"]
    assert "Eq. (1)" not in meta["catch"]
    assert "Eq. (3) fails." in meta["catch"]


def test_publish_without_meta_still_replies(tmp_path):
    root = REPO / "runs" / SLUG
    folder = tmp_path / "src"
    shutil.copytree(root, folder, ignore=shutil.ignore_patterns("__pycache__", "meta.json"))
    (folder / "report.html").write_text(
        "<h2>Summary</h2><p>Eq. (3) and Eq. (4) fail.</p>"
        "<h2>The catch</h2><p>Eq. (3) and Eq. (4) fail.</p>",
        encoding="utf-8",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in folder.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    repo = tmp_path / "empty"
    repo.mkdir()
    bot = Publisher(repo, dry_run=True, fetch=False, push=False)
    out = bot.handle(_message(9), {"zip": buffer.getvalue()}, now=0)
    url = f"https://ilkhamfy.github.io/sanity/papers.html?paper={SLUG}"
    assert _headers(out) == [f"sanity run={SLUG} to=writer status=published url={url}"]
