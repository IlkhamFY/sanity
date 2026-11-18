"""The runner trusts only a printed VERDICT line."""

import json
import shutil
from pathlib import Path

import jsonschema
import sympy as sp

from check_template import NUMERIC_POINTS, sample_relative_error
from verify_run import main, parse_verdict, script_constants

REPO = Path(__file__).resolve().parents[2]
VERDICTS_SCHEMA = REPO / "docs" / "schemas" / "verdicts.schema.json"


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


def _check(checks, name, line, engine="sympy", claim="1"):
    header = f'ENGINE = "{engine}"\nCLAIM = {claim!r}\n'
    (checks / name).write_text(header + f'print("{line}")\n', encoding="utf-8")


def test_runner_writes_results_and_exits_on_failure(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_ok.py", "VERDICT: VERIFIED 01_ok | symbolic")
    _check(checks, "02_num.py", "VERDICT: VERIFIED-NUMERICALLY 02_num | 200 points, max rel err 0", engine="scipy")
    _check(checks, "03_lean.py", "VERDICT: Lean-PROVED 03_lean | theorem accepted", engine="lean")
    _check(checks, "04_open.py", "VERDICT: UNCHECKED 04_open | missing assumption")
    snapshot = tmp_path / "snap"
    assert main([str(tmp_path), "--snapshot", str(snapshot)]) == 0
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "Lean-PROVED: 1" in results
    assert "VERIFIED-NUMERICALLY: 1" in results
    assert "UNCHECKED: 1" in results
    assert "| 03_lean | (1) | Lean-PROVED | confirmed | yes |" in results
    assert "| 01_ok | (1) | VERIFIED | rejected | no |" in results
    assert (snapshot / "RESULTS.md").read_text(encoding="utf-8") == results
    assert (snapshot / "verdicts.json").read_text(encoding="utf-8") == (
        tmp_path / "verdicts.json"
    ).read_text(encoding="utf-8")

    _check(checks, "05_bad.py", "VERDICT: FAILED 05_bad | at x=1: lhs 2, rhs 1")
    assert main([str(tmp_path), "--only", "05_bad"]) == 1


def test_verdicts_json_matches_schema_and_records_engine(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_fail.py", "VERDICT: FAILED 01_fail | gap 1", engine="scipy", claim="2")
    _check(checks, "02_support.py", "VERDICT: VERIFIED 02_support | ok", claim=None)
    (checks / "03_bare.py").write_text('print("VERDICT: VERIFIED 03_bare | ok")\n', encoding="utf-8")
    (checks / "04_silent.py").write_text('print("nothing")\n', encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    data = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, json.loads(VERDICTS_SCHEMA.read_text(encoding="utf-8")))
    by_id = {row["check_id"]: row for row in data["verdicts"]}
    assert by_id["01_fail"]["engine"] == "scipy"
    assert by_id["01_fail"]["claim"] == "2"
    assert by_id["01_fail"]["ruling"] == "confirmed"
    assert by_id["01_fail"]["script"] == f"{tmp_path.name}/checks/01_fail.py"
    assert by_id["02_support"]["claim"] is None
    assert by_id["02_support"]["ruling"] is None
    assert by_id["03_bare"]["engine"] == "unspecified"
    assert by_id["04_silent.py"]["verdict"] == "ERROR"
    assert data["counts"]["FAILED"] == 1 and data["counts"]["ERROR"] == 1
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "| 02_support | supporting |" in results
    assert "| 02_support | (" not in results.split("## Rulings")[1]


def test_constants_are_read_without_running_the_script(tmp_path):
    script = tmp_path / "x.py"
    script.write_text(
        'import sys\nENGINE = "lean"\nCLAIM = "7"\nsys.exit("would fail if run")\n',
        encoding="utf-8",
    )
    assert script_constants(script) == {"ENGINE": "lean", "CLAIM": "7"}


def _run_with_equations(tmp_path, equations, claim):
    (tmp_path / "equations.json").write_text(json.dumps(equations), encoding="utf-8")
    verify = tmp_path / "verify"
    (verify / "checks").mkdir(parents=True)
    _check(verify / "checks", "01_x.py", "VERDICT: VERIFIED 01_x | ok", claim=claim)
    return main([str(verify)])


EQUATIONS = {
    "slug": "toy",
    "source": "toy.tex",
    "equations": [{"number": "1", "line": 3, "latex": "a=b"}],
}


def test_valid_equations_and_known_claim_run(tmp_path):
    assert _run_with_equations(tmp_path, EQUATIONS, "1") == 0
    data = json.loads((tmp_path / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    assert data["paper"] == tmp_path.name


def test_unknown_claim_stops_before_running(tmp_path, capsys):
    assert _run_with_equations(tmp_path, EQUATIONS, "9") == 2
    assert "CLAIM '9'" in capsys.readouterr().err
    assert not (tmp_path / "verify" / "RESULTS.md").exists()


def test_invalid_equations_stop_before_running(tmp_path, capsys):
    broken = {"slug": "toy", "source": "toy.tex", "equations": [{"number": "1", "latex": "a=b"}]}
    assert _run_with_equations(tmp_path, broken, "1") == 2
    assert "line" in capsys.readouterr().err


def test_specimen_checks_flag_the_planted_errors(tmp_path):
    source = REPO / "runs" / "example-oscillator" / "verify" / "checks"
    shutil.copytree(source, tmp_path / "checks")
    assert main([str(tmp_path), "--only", "01_"]) == 0
    assert main([str(tmp_path), "--only", "02_"]) == 1
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "m=k=v=x=1" in text
    assert "| 02_eq3_paper_energy_step | (3) | FAILED | confirmed | no |" in text
    assert main([str(tmp_path), "--only", "03_"]) == 1
    assert "not T" in (tmp_path / "RESULTS.md").read_text(encoding="utf-8")


def test_specimen_run_validates_and_writes_verdicts(tmp_path):
    run = tmp_path / "example-oscillator"
    shutil.copytree(REPO / "runs" / "example-oscillator", run)
    assert main([str(run / "verify")]) == 1
    data = json.loads((run / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, json.loads(VERDICTS_SCHEMA.read_text(encoding="utf-8")))
    rulings = {row["check_id"]: (row["claim"], row["engine"], row["ruling"]) for row in data["verdicts"]}
    assert rulings == {
        "01_eq3_energy_step": (None, "sympy", None),
        "02_eq3_paper_energy_step": ("3", "sympy", "confirmed"),
        "03_eq4_decay_units": ("4", "python", "confirmed"),
    }
