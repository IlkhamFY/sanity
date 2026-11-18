"""The conversation log is append-only JSON lines with a fixed vocabulary."""

import datetime
import json

import pytest

from conversation import ConversationError, append, main, open_questions, questions_asked, read

NOW = datetime.datetime(2026, 11, 18, 14, 2, 11, tzinfo=datetime.timezone.utc)


def test_append_and_read(tmp_path):
    reply = tmp_path / "equations.json"
    reply.write_text("{}", encoding="utf-8")
    append(tmp_path, "verifier", "question", "Does the paper state k H >> 1?", eq="12",
           sender="@verifier", message_id=812, reply_to=790, now=NOW)
    append(tmp_path, "reader", "answer", "Yes, section 3.", reply_to=812, files=[reply], now=NOW)
    entries = read(tmp_path)
    assert [e["kind"] for e in entries] == ["question", "answer"]
    assert entries[0]["time"] == "2026-11-18T14:02:11+00:00"
    assert entries[1]["files"][0]["name"] == "equations.json"
    assert len(entries[1]["files"][0]["sha256"]) == 64
    lines = (tmp_path / "conversation.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line) for line in lines)


def test_open_questions_by_reply_id(tmp_path):
    append(tmp_path, "verifier", "question", "q1", eq="1", message_id=1)
    append(tmp_path, "verifier", "question", "q2", eq="2", message_id=2)
    append(tmp_path, "reader", "answer", "a1", reply_to=1)
    assert questions_asked(tmp_path) == 2
    assert [q["text"] for q in open_questions(tmp_path)] == ["q2"]


def test_open_questions_without_ids_use_order(tmp_path):
    append(tmp_path, "verifier", "question", "q1", eq="1")
    assert len(open_questions(tmp_path)) == 1
    append(tmp_path, "reader", "answer", "a1")
    assert open_questions(tmp_path) == []


@pytest.mark.parametrize(
    "args, message",
    [
        (("judge", "note", "x"), "role must be"),
        (("verifier", "chat", "x"), "kind must be"),
        (("reader", "question", "x"), "only the verifier asks"),
        (("verifier", "question", "x"), "must name the equation"),
    ],
)
def test_bad_entries_are_rejected(tmp_path, args, message):
    with pytest.raises(ConversationError, match=message):
        append(tmp_path, *args)


def test_missing_folder_is_rejected(tmp_path):
    with pytest.raises(ConversationError, match="no such attempt folder"):
        append(tmp_path / "nope", "verifier", "note", "x")


def test_cli(tmp_path, capsys):
    assert main(["add", "--dir", str(tmp_path), "--role", "human", "--kind", "command", "--text", "stop toy"]) == 0
    capsys.readouterr()
    assert main(["show", "--dir", str(tmp_path)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["questions_asked"] == 0 and shown["entries"][0]["kind"] == "command"
    assert main(["add", "--dir", str(tmp_path), "--role", "reader", "--kind", "question", "--text", "x"]) == 1
