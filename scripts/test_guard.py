"""The publish guard accepts this repo and rejects a bad bundle."""

import json
import shutil

from guard import (
    _script_errors,
    external_script_errors,
    report_section_text,
    report_url_errors,
    summary_errors,
    validate_repo,
)
from publish_run import REPO


def test_this_repo_passes():
    assert validate_repo(REPO) == []


def test_summary_may_name_only_fails():
    fails = {"4.4"}
    assert summary_errors("Eq. (4.4) fails.", fails, "judgement") == []
    named = summary_errors("Eq. (4.3) holds and Eq. (4.4) fails.", fails, "judgement")
    assert any("4.3" in line for line in named)
    html = "<h2>Summary</h2><p>Eq. (4.3) holds.</p><h2>Claims</h2><p>(4.5) HOLDS</p>"
    assert "4.3" in report_section_text(html)
    assert "4.5" not in report_section_text(html)


def test_report_urls_allow_fonts_and_katex_only():
    assert report_url_errors('<link href="https://fonts.googleapis.com/css?family=x">', "report.html") == []
    assert report_url_errors('<link href="https://fonts.gstatic.com/s/a.woff2">', "report.html") == []
    katex = '<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>'
    assert report_url_errors(katex, "report.html") == []
    blocked = report_url_errors('<a href="https://example.com/paper">', "report.html")
    assert blocked and "example.com" in blocked[0]
    script = '<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>'
    assert external_script_errors(script, "report.html")
    assert external_script_errors("<script>document.body</script>", "report.html") == []


def test_holds_needs_a_script(tmp_path):
    verdicts = {
        "claims": [{
            "claim": "1",
            "verdict": "HOLDS",
            "evidence": {"kind": "symbolic", "script": "verify/checks/missing.py"},
        }],
        "checks": [],
    }
    errors = _script_errors(tmp_path, verdicts)
    assert any("missing" in error for error in errors)


def test_file_meta_example_is_accepted(tmp_path):
    slug = "example-oscillator"
    shutil.copytree(REPO / "runs" / slug, tmp_path / "runs" / slug)
    meta = {
        "title": "A spring, missing a half",
        "authors": ["unknown"],
        "abstract": "",
        "arxiv_id": None,
        "version": None,
        "primary_category": None,
        "doi": None,
        "journal_ref": None,
        "fetched_at": "2026-11-19T00:00:00Z",
        "slug": slug,
        "subject": "unknown",
        "example": True,
        "source": "file",
    }
    (tmp_path / "runs" / slug / "source").mkdir()
    (tmp_path / "runs" / slug / "source" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    papers = json.loads((REPO / "site" / "public" / "data" / "papers.json").read_text(encoding="utf-8"))
    row = next(paper for paper in papers["papers"] if paper["slug"] == slug)
    data = tmp_path / "site" / "public" / "data"
    data.mkdir(parents=True)
    (data / "papers.json").write_text(json.dumps({"papers": [row]}), encoding="utf-8")
    (data / "activity.json").write_text('{"events": []}', encoding="utf-8")
    assert validate_repo(tmp_path) == []
    assert row["example"] is True


def test_count_mismatch_fails(tmp_path):
    shutil.copytree(REPO / "runs" / "example-oscillator", tmp_path / "runs" / "example-oscillator")
    papers = json.loads((REPO / "site" / "public" / "data" / "papers.json").read_text(encoding="utf-8"))
    row = next(paper for paper in papers["papers"] if paper["slug"] == "example-oscillator")
    row = json.loads(json.dumps(row))
    row["counts"]["fails"] = 9
    data = tmp_path / "site" / "public" / "data"
    data.mkdir(parents=True)
    (data / "papers.json").write_text(json.dumps({"papers": [row]}), encoding="utf-8")
    (data / "activity.json").write_text(
        (REPO / "site" / "public" / "data" / "activity.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    errors = validate_repo(tmp_path)
    assert any("counts" in error and "example-oscillator" in error for error in errors)
