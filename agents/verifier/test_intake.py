"""Received equations are hashed, validated, versioned, and their state is on disk."""

import hashlib
import json
from pathlib import Path

import pytest

from intake import IntakeError, main, receive, status

REPO = Path(__file__).resolve().parents[2]
SPECIMEN = REPO / "runs" / "example-oscillator" / "equations.json"


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def toy(slug="toy", latex="a=b"):
    return {"slug": slug, "source": "toy.tex", "equations": [{"number": "1", "line": 1, "latex": latex}]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_first_file_starts_attempt_one(tmp_path):
    scratch = tmp_path / "scratch"
    got = receive(scratch, "example-oscillator", SPECIMEN, expected_sha256=sha(SPECIMEN))
    assert (got.attempt, got.version, got.equations, got.duplicate) == (1, 1, 5, False)
    folder = scratch / "example-oscillator" / "1"
    assert (folder / "equations.v1.json").read_bytes() == SPECIMEN.read_bytes()
    assert (folder / "equations.json").read_bytes() == SPECIMEN.read_bytes()
    assert (folder / "verify" / "checks").is_dir()


def test_answer_with_new_file_becomes_next_version(tmp_path):
    first = write(tmp_path / "a.json", toy())
    second = write(tmp_path / "b.json", toy(latex="a=2b"))
    receive(tmp_path / "s", "toy", first)
    got = receive(tmp_path / "s", "toy", second)
    assert (got.attempt, got.version) == (1, 2)
    assert json.loads((tmp_path / "s" / "toy" / "1" / "equations.json").read_text())["equations"][0]["latex"] == "a=2b"


def test_identical_file_is_not_stored_twice(tmp_path):
    first = write(tmp_path / "a.json", toy())
    receive(tmp_path / "s", "toy", first)
    got = receive(tmp_path / "s", "toy", first)
    assert got.duplicate and got.version == 1
    assert len(list((tmp_path / "s" / "toy" / "1").glob("equations.v*.json"))) == 1


def test_finished_attempt_and_rerun_rules(tmp_path):
    scratch = tmp_path / "s"
    first = write(tmp_path / "a.json", toy())
    receive(scratch, "toy", first)
    (scratch / "toy" / "1" / "verify" / "verdicts.json").write_text("{}", encoding="utf-8")

    same = receive(scratch, "toy", first)
    assert same.duplicate and same.attempt == 1 and same.already_verified_in == 1

    changed = receive(scratch, "toy", write(tmp_path / "b.json", toy(latex="a=c")))
    assert (changed.attempt, changed.version, changed.duplicate) == (2, 1, False)

    rerun = receive(scratch, "toy", first, new_attempt=True)
    assert (rerun.attempt, rerun.already_verified_in) == (3, 1)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"expected_sha256": "0" * 64}, "sha256 mismatch"),
        ({"slug": "other"}, "message says 'other'"),
        ({"slug": "Bad_Slug"}, "invalid slug"),
    ],
)
def test_rejections(tmp_path, kwargs, message):
    path = write(tmp_path / "a.json", toy())
    slug = kwargs.pop("slug", "toy")
    with pytest.raises(IntakeError, match=message):
        receive(tmp_path / "s", slug, path, **kwargs)
    assert not (tmp_path / "s" / "toy").exists()


def test_invalid_equations_are_rejected_with_the_reason(tmp_path):
    bad = toy()
    bad["equations"][0]["sympy"] = {"lhs": "a", "rhs": "__import__('os')", "symbols": {"a": []}}
    with pytest.raises(IntakeError, match="disallowed syntax|undeclared name"):
        receive(tmp_path / "s", "toy", write(tmp_path / "a.json", bad))


def test_status_reports_state_from_disk(tmp_path):
    scratch = tmp_path / "s"
    receive(scratch, "toy", write(tmp_path / "a.json", toy()))
    folder = scratch / "toy" / "1"
    (folder / "verify" / "PLAN.md").write_text("plan", encoding="utf-8")
    (folder / "verify" / "checks" / "01_x.py").write_text("", encoding="utf-8")
    (folder / "conversation.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    state = status(scratch, "toy")
    [attempt] = state["attempts"]
    assert attempt["versions"] == [1]
    assert attempt["plan"] and attempt["checks"] == 1
    assert attempt["verdicts"] is False and attempt["bundle"] is None
    assert attempt["conversation_entries"] == 2


def test_cli_prints_json_and_exit_codes(tmp_path, capsys):
    path = write(tmp_path / "a.json", toy())
    assert main(["receive", "--slug", "toy", "--file", str(path), "--scratch", str(tmp_path / "s")]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == 1
    assert main(["receive", "--slug", "toy", "--file", str(path), "--sha256", "f" * 64,
                 "--scratch", str(tmp_path / "s")]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err
    assert main(["status", "--slug", "toy", "--scratch", str(tmp_path / "s")]) == 0
    assert json.loads(capsys.readouterr().out)["attempts"][0]["attempt"] == 1
