"""The runner trusts only a printed VERDICT line."""

import sympy as sp

from check_template import NUMERIC_POINTS, sample_relative_error
from verify_run import main, parse_verdict


def test_parse_accepts_one_verdict_line():
    text = "noise\nVERDICT: Lean-PROVED 04_eq3_lean | paper_potential_drops_a_half\n"
    assert parse_verdict(text) == (
        "Lean-PROVED",
        "04_eq3_lean",
        "paper_potential_drops_a_half",
    )
    assert parse_verdict("VERDICT: VERIFIED a | ok\nVERDICT: FAILED b | no") is None
    assert parse_verdict("no verdict here") is None


def test_numeric_sample_uses_two_hundred_points_and_a_fixed_seed():
    x = sp.symbols("x", positive=True)
    worst, point = sample_relative_error(x / x, sp.Integer(1), (x,), {x: (0.1, 3.0)})
    again, _ = sample_relative_error(x / x, sp.Integer(1), (x,), {x: (0.1, 3.0)})
    assert NUMERIC_POINTS == 200
    assert worst == 0
    assert again == worst
    assert set(point) == {x}

    worst_broken, counterexample = sample_relative_error(x + 1, x, (x,), {x: (0.1, 3.0)})
    assert worst_broken > 1e-8
    assert counterexample is not None


def test_runner_writes_results_and_exits_on_failure(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "01_ok.py").write_text(
        'print("VERDICT: VERIFIED 01_ok | symbolic")\n',
        encoding="utf-8",
    )
    (checks / "02_num.py").write_text(
        'print("VERDICT: VERIFIED-NUMERICALLY 02_num | 200 points, max rel err 0")\n',
        encoding="utf-8",
    )
    (checks / "03_lean.py").write_text(
        'print("VERDICT: Lean-PROVED 03_lean | theorem accepted")\n',
        encoding="utf-8",
    )
    (checks / "04_open.py").write_text(
        'print("VERDICT: UNCHECKED 04_open | missing assumption")\n',
        encoding="utf-8",
    )
    snapshot = tmp_path / "snap"
    assert main([str(tmp_path), "--snapshot", str(snapshot)]) == 0
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "Lean-PROVED: 1" in results
    assert "VERIFIED-NUMERICALLY: 1" in results
    assert "UNCHECKED: 1" in results
    assert "| 03_lean | Lean-PROVED | confirmed | yes |" in results
    assert "| 01_ok | VERIFIED | rejected | no |" in results
    assert (snapshot / "RESULTS.md").read_text(encoding="utf-8") == results

    (checks / "05_bad.py").write_text(
        'print("VERDICT: FAILED 05_bad | at x=1: lhs 2, rhs 1")\n',
        encoding="utf-8",
    )
    assert main([str(tmp_path), "--only", "05_bad"]) == 1


def test_specimen_checks_flag_the_planted_errors(tmp_path):
    import shutil

    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "runs"
        / "example-oscillator"
        / "verify"
        / "checks"
    )
    shutil.copytree(source, tmp_path / "checks")
    assert main([str(tmp_path), "--only", "01_"]) == 0
    assert main([str(tmp_path), "--only", "02_"]) == 1
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "m=k=v=x=1" in text
    assert "| 02_eq3_paper_energy_step | FAILED | confirmed | no |" in text
    assert main([str(tmp_path), "--only", "03_"]) == 1
    assert "not T" in (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
