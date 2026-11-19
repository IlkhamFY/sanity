"""The publisher writes the public index from a run folder, and only from that."""

import json
from pathlib import Path

import pytest

from paper_preview import render_equation, render_preview
from publish_run import (
    events_from_run,
    is_epjc,
    judgement_of,
    main,
    marks_of,
    publish,
    tally,
)

REPO = Path(__file__).resolve().parents[1]


def test_judgement_is_the_telegram_sentence():
    text = "arxiv-2410-11128: Eq. (4.4) in v1 fails.\n\n(4.4) FAILS — counterexample.\n"
    assert judgement_of(text, None, "arxiv-2410-11128") == "Eq. (4.4) in v1 fails."
    assert judgement_of(None, "Judgement: The note is a toy.\n", "example") == "The note is a toy."
    assert judgement_of(None, "No sentence here.\n", "example") is None


def test_tally_counts_claims_and_promotes_a_broken_check():
    verdicts = {
        "claims": [
            {"claim": "1", "verdict": "HOLDS"},
            {"claim": "2", "verdict": "UNCHECKED"},
        ],
        "checks": [
            {"role": "claim", "claim": "2", "verdict": "ERROR"},
        ],
    }
    counts, segments = tally(verdicts)
    assert counts == {"holds": 1, "fails": 0, "unchecked": 0, "error": 1}
    assert segments == ["HOLDS", "ERROR"]


def test_epjc_mark_follows_the_doi():
    logos = REPO / "site" / "public" / "logos"
    assert is_epjc("European Journal of Physics C, vol: 85", "10.1140/epjc/s10052-025-14303-w")
    assert not is_epjc("Journal of Physics A", None)
    marks = marks_of(
        "https://arxiv.org/abs/2410.11128v1",
        "European Journal of Physics C",
        "10.1140/epjc/s10052-025-14303-w",
        logos,
    )
    assert [mark["name"] for mark in marks] == ["arXiv", "Springer"]


def test_publish_is_idempotent_and_keeps_real_timestamps(tmp_path):
    data = tmp_path / "data"
    logos = REPO / "site" / "public" / "logos"
    run = REPO / "runs" / "arxiv-2410-11128"
    first = publish(run, "Astrophysics / General relativity", None, None, False, data, logos, preview=False, network=False)
    second = publish(run, "Astrophysics / General relativity", None, None, False, data, logos, preview=False, network=False)
    papers = json.loads((data / "papers.json").read_text(encoding="utf-8"))["papers"]
    assert len(papers) == 1
    assert first == second
    assert first["slug"] == "arxiv-2410-11128"
    assert first["counts"] == {"holds": 5, "fails": 1, "unchecked": 2, "error": 0}
    assert first["segments"].count("FAILS") == 1
    assert first["checked_at"] == "2026-11-18T22:38:34"
    assert first["judgement"] == "Eq. (4.4) in v1 fails."
    assert first["flags"][0]["claim"] == "4.4"
    assert first["flags"][0]["line"] == 636
    assert first["flags"][0]["corrected"] is True
    assert "authors" not in first
    assert {tool["name"] for tool in first["tools"]} == {"SymPy", "Lean", "Python"}
    assert first["telegram"]["role"] == "writer"
    assert "Eq. (4.4) in v1 fails." in first["telegram"]["lines"][0]
    events = json.loads((data / "activity.json").read_text(encoding="utf-8"))["events"]
    assert len(events) == 2
    assert {event["role"] for event in events} == {"verifier", "writer"}
    assert "2026-11-18T22:38:34" in {event["time"] for event in events}
    assert (data / "arxiv-2410-11128" / "equations.json").is_file()
    assert (data / "arxiv-2410-11128" / "verdicts.json").is_file()
    assert (data / "arxiv-2410-11128" / "REPORT.md").is_file()


def test_example_run_is_marked_and_has_no_invented_url(tmp_path):
    data = tmp_path / "data"
    publish(
        REPO / "runs" / "example-oscillator",
        "Physics",
        None,
        None,
        True,
        data,
        REPO / "site" / "public" / "logos",
        preview=False,
        network=False,
    )
    paper = json.loads((data / "papers.json").read_text(encoding="utf-8"))["papers"][0]
    assert paper["example"] is True
    assert paper["subject"] == "Physics"
    assert "source_url" not in paper
    assert "preview" not in paper
    assert paper["counts"]["fails"] == 2
    assert "authors" not in paper


def test_missing_verdicts_stay_checking(tmp_path):
    run = tmp_path / "open-note"
    run.mkdir()
    equations = json.loads((REPO / "runs" / "example-oscillator" / "equations.json").read_text(encoding="utf-8"))
    equations["slug"] = "open-note"
    (run / "equations.json").write_text(json.dumps(equations), encoding="utf-8")
    entry = publish(run, "Math", None, None, False, tmp_path / "data", tmp_path / "logos", preview=False, network=False)
    assert entry["status"] == "checking"
    assert entry["segments"] == ["PENDING"] * 5
    assert json.loads((tmp_path / "data" / "activity.json").read_text(encoding="utf-8"))["events"] == []


def test_event_mode_appends_once(tmp_path):
    data = tmp_path / "data"
    assert main(["--event", "--slug", "open-note", "--role", "reader", "--message", "Reader extracted 8 claims", "--time", "2026-11-19T03:00:00Z", "--data-dir", str(data)]) == 0
    main(["--event", "--slug", "open-note", "--role", "reader", "--message", "Reader extracted 8 claims", "--time", "2026-11-19T03:00:00Z", "--data-dir", str(data)])
    main(["--event", "--slug", "open-note", "--role", "verifier", "--message", "Eq. (4.4) FAILS", "--detail", "counterexample", "--time", "2026-11-19T03:05:00Z", "--data-dir", str(data)])
    events = json.loads((data / "activity.json").read_text(encoding="utf-8"))["events"]
    assert len(events) == 2
    assert events[0]["event"] == "Reader extracted 8 claims"
    assert events[1]["detail"] == "counterexample"


def test_schema_rejects_a_broken_equations_file(tmp_path):
    run = tmp_path / "bad"
    run.mkdir()
    (run / "equations.json").write_text('{"slug": "Bad Slug", "source": "x", "equations": []}', encoding="utf-8")
    with pytest.raises(SystemExit):
        publish(run, "Physics", None, None, False, tmp_path / "data", tmp_path, preview=False, network=False)


def test_report_html_is_linked(tmp_path):
    run = tmp_path / "with-report"
    run.mkdir()
    equations = json.loads((REPO / "runs" / "example-oscillator" / "equations.json").read_text(encoding="utf-8"))
    equations["slug"] = "with-report"
    (run / "equations.json").write_text(json.dumps(equations), encoding="utf-8")
    shutil_copy = REPO / "runs" / "example-oscillator" / "verify" / "verdicts.json"
    # verdicts.json "paper" need not equal the slug for the schema.
    (run / "verdicts.json").write_text(shutil_copy.read_text(encoding="utf-8"), encoding="utf-8")
    (run / "report.html").write_text("<p>Report</p>", encoding="utf-8")
    entry = publish(run, "Physics", None, None, False, tmp_path / "data", tmp_path / "logos", preview=False, network=False)
    assert entry["report"] == "with-report/report.html"
    assert (tmp_path / "data" / "with-report" / "report.html").is_file()


def test_events_omit_a_reader_step_with_no_timestamp():
    events = events_from_run(Path("/no/such/run"), "x", {"generated_at": "2026-11-18T00:00:00", "claims": [], "checks": []}, None)
    assert [event["role"] for event in events] == ["verifier"]


def test_equation_crop_needs_a_real_tag(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("PIL")
    pdf = tmp_path / "note.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 400), "(4.4) mentioned in a sentence")
    page.insert_text((470, 400), "(4.4)")
    page.insert_text((72, 120), "Abstract")
    page.insert_text((72, 160), "A short abstract line.")
    document.save(pdf)
    document.close()
    dest = tmp_path / "eq.webp"
    assert render_equation(pdf, dest, "4.4") == 1
    assert dest.is_file()
    assert render_equation(pdf, tmp_path / "missing.webp", "9.9") is None
    preview = tmp_path / "preview.webp"
    render_preview(pdf, preview)
    assert preview.stat().st_size > 100
