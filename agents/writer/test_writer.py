"""The Writer copies verdicts and does not invent new ones."""

import json
from pathlib import Path

from reports import ReportRow, render_report, render_telegram


def _row(verdict: str) -> ReportRow:
    return ReportRow(
        equation="3",
        line=17,
        wrong_latex="E=\\tfrac{1}{2}mv^{2}+kx^{2}",
        corrected_latex="E=\\tfrac{1}{2}mv^{2}+\\tfrac{1}{2}kx^{2}",
        verdict=verdict,
        check_id="02_eq3_paper_energy_step",
        script="verify/checks/02_eq3_paper_energy_step.py",
        effect="propagates",
        detail="gap at m=k=v=x=1",
    )


def test_report_copies_the_verdict_unchanged():
    report = render_report("example-oscillator", "Example.", [_row("FAILED")], [])
    assert "**FAILED**" in report
    assert "VERIFIED" not in report
    assert "error that propagates" in report
    assert "verify/checks/02_eq3_paper_energy_step.py" in report
    assert "Wrong:" in report
    assert "Corrected:" in report
    telegram = render_telegram("example-oscillator", [_row("FAILED")])
    assert "FAILED" in telegram
    assert "propagates" in telegram


def test_passing_verdict_is_not_relabeled():
    report = render_report(
        "example-oscillator",
        "Example.",
        [],
        ["(3) corrected — VERIFIED (`01_eq3_energy_step`)"],
    )
    assert "VERIFIED" in report
    assert "FAILED" not in report


def test_example_run_keeps_script_verdicts():
    run = Path(__file__).resolve().parents[2] / "runs" / "example-oscillator"
    results = (run / "verify" / "RESULTS.md").read_text(encoding="utf-8")
    report = (run / "REPORT.md").read_text(encoding="utf-8")
    telegram = (run / "telegram.md").read_text(encoding="utf-8")
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    equations = json.loads((run / "equations.json").read_text(encoding="utf-8"))
    # RESULTS.md uses the Verifier's HOLDS/FAILS names; REPORT.md still uses the old ones
    # until the Writer is updated to read verify/verdicts.json.
    for verdict in ("HOLDS", "FAILS"):
        assert verdict in results
    for verdict in ("VERIFIED", "FAILED"):
        assert verdict in report
    assert "FAILED" in telegram
    assert "typo" in report.lower()
    assert "propagat" in report.lower()
    assert "verify/checks/02_eq3_paper_energy_step.py" in report
    assert "verify/checks/03_eq4_decay_units.py" in report
    assert status["stage"] == "done"
    assert status["paper"] == "example-oscillator"
    for key in ("paper", "stage", "owner_bot", "updated_at", "commit", "notes"):
        assert key in status
    assert {item["number"] for item in equations["equations"]} == {"1", "2", "3", "4", "5"}
    note = (run / "note.tex").read_text(encoding="utf-8").splitlines()
    for item in equations["equations"]:
        assert note[item["line"] - 1] == item["latex"]
