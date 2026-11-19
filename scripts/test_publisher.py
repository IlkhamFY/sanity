"""Publisher parsing, validation, and idempotent commits. No network."""

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from fetch_paper import classify
from publisher import PUSH, Publisher, parse_header, read_bot_token
from publish_run import REPO

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


def _texts(pairs) -> list[str]:
    return [text for _chat, text in pairs]


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
