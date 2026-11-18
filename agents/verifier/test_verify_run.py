"""The runner trusts only a printed VERDICT line."""

import json
import shutil
from pathlib import Path

import jsonschema
import pytest
import sympy as sp

from check_template import NUMERIC_POINTS, sample_relative_error
from verify_run import main, parse_verdict, script_constants

REPO = Path(__file__).resolve().parents[2]
VERDICTS_SCHEMA = REPO / "docs" / "schemas" / "verdicts.schema.json"


def schema_check(data):
    jsonschema.validate(data, json.loads(VERDICTS_SCHEMA.read_text(encoding="utf-8")))


def test_parse_accepts_one_verdict_line():
    text = "noise\nVERDICT: FAILS 02_eq3 counterexample | at x=1: 3/2 vs 1\n"
    assert parse_verdict(text) == ("FAILS", "02_eq3", "counterexample", "at x=1: 3/2 vs 1")
    assert "found 2" in parse_verdict("VERDICT: HOLDS a symbolic | ok\nVERDICT: FAILS b symbolic | no")
    assert "found 0" in parse_verdict("no verdict here")


@pytest.mark.parametrize(
    "line, problem",
    [
        ("VERDICT: VERIFIED a | ok", "malformed"),
        ("VERDICT: HOLDS a | ok", "malformed"),
        ("VERDICT: HOLDS a counterexample | ok", "does not fit"),
        ("VERDICT: UNCHECKED a symbolic | ok", "does not fit"),
        ("VERDICT: HOLDS a proof | theorem accepted", "reserved for lean_check"),
        ("VERDICT: FAILS a refutation | negation proved", "reserved for lean_check"),
    ],
)
def test_parse_rejects_bad_lines(line, problem):
    assert problem in parse_verdict(line)


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


def _check(checks, name, line, engine="sympy", **constants):
    header = f'ENGINE = "{engine}"\n'
    for key, value in constants.items():
        header += f"{key} = {value!r}\n"
    (checks / name).write_text(header + f"print({line!r})\n", encoding="utf-8")


def test_runner_writes_results_and_exits_on_failure(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_ok.py", "VERDICT: HOLDS 01_ok symbolic | simplify", CLAIM="1")
    _check(checks, "02_num.py", "VERDICT: HOLDS 02_num numerical | 200 points", engine="scipy", CLAIM="2")
    _check(checks, "03_open.py", "VERDICT: UNCHECKED 03_open none | regime not stated", CLAIM="3")
    snapshot = tmp_path / "snap"
    assert main([str(tmp_path), "--snapshot", str(snapshot)]) == 0
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "Claims: HOLDS: 2 · FAILS: 0 · UNCHECKED: 1" in results
    assert "| (2) | **HOLDS** | numerical | 02_num |" in results
    assert "| (3) | **UNCHECKED** | none | 03_open |" in results
    assert (snapshot / "RESULTS.md").read_text(encoding="utf-8") == results
    assert (snapshot / "verdicts.json").read_text(encoding="utf-8") == (
        tmp_path / "verdicts.json"
    ).read_text(encoding="utf-8")

    _check(checks, "04_bad.py", "VERDICT: FAILS 04_bad counterexample | at x=1: 2 vs 1", CLAIM="4")
    assert main([str(tmp_path), "--only", "04_bad"]) == 1


def test_verdicts_json_per_claim_and_per_check(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_num.py", "VERDICT: HOLDS 01_num numerical | sampled", CLAIM="1")
    _check(checks, "02_sym.py", "VERDICT: HOLDS 02_sym symbolic | exact", CLAIM="1")
    _check(checks, "03_fail.py", "VERDICT: FAILS 03_fail counterexample | at x=1", engine="scipy", CLAIM="2")
    _check(checks, "04_fix.py", "VERDICT: HOLDS 04_fix symbolic | fixed", CORRECTS="2", CORRECTION="a=2b")
    _check(checks, "05_support.py", "VERDICT: HOLDS 05_support symbolic | lemma")
    (checks / "06_silent.py").write_text('CLAIM = "3"\nprint("nothing")\n', encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    data = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    schema_check(data)
    claims = {c["claim"]: c for c in data["claims"]}
    assert list(claims) == ["1", "2", "3"]
    assert claims["1"]["verdict"] == "HOLDS"
    assert claims["1"]["evidence"]["kind"] == "symbolic"
    assert claims["1"]["evidence"]["check_id"] == "02_sym"
    assert claims["1"]["correction"] is None
    assert claims["2"]["verdict"] == "FAILS"
    assert claims["2"]["evidence"]["engine"] == "scipy"
    assert claims["2"]["evidence"]["script"] == "verify/checks/03_fail.py"
    assert claims["2"]["correction"] == {
        "latex": "a=2b",
        "check_id": "04_fix",
        "verified": True,
        "evidence": "symbolic",
        "detail": "fixed",
    }
    assert claims["3"]["verdict"] == "UNCHECKED"
    assert "check broken" in claims["3"]["evidence"]["detail"]
    roles = {c["check_id"]: (c["role"], c["claim"]) for c in data["checks"]}
    assert roles["04_fix"] == ("correction", "2")
    assert roles["05_support"] == ("supporting", None)
    assert roles["06_silent.py"] == ("claim", "3")
    assert data["counts"]["claims"] == {"HOLDS": 1, "FAILS": 1, "UNCHECKED": 1}
    assert data["counts"]["checks"]["ERROR"] == 1
    results = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "`a=2b` (verified, 04_fix)" in results


def test_failing_correction_is_reported_unverified(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_fail.py", "VERDICT: FAILS 01_fail symbolic | residual 1", CLAIM="1")
    _check(checks, "02_fix.py", "VERDICT: FAILS 02_fix symbolic | still wrong", CORRECTS="1", CORRECTION="a=c")
    assert main([str(tmp_path)]) == 1
    data = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    assert data["claims"][0]["correction"]["verified"] is False
    assert "NOT verified" in (tmp_path / "RESULTS.md").read_text(encoding="utf-8")


def test_disagreeing_checks_are_a_conflict(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_a.py", "VERDICT: HOLDS 01_a symbolic | ok", CLAIM="1")
    _check(checks, "02_b.py", "VERDICT: FAILS 02_b counterexample | at x=2", CLAIM="1")
    assert main([str(tmp_path)]) == 1
    claim = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))["claims"][0]
    assert claim["verdict"] == "UNCHECKED" and claim["conflict"] is True


def test_plain_script_cannot_claim_a_lean_proof(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    _check(checks, "01_fake.py", "VERDICT: HOLDS 01_fake proof | theorem accepted", engine="lean", CLAIM="1")
    assert main([str(tmp_path)]) == 1
    data = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    assert data["checks"][0]["verdict"] == "ERROR"
    assert data["claims"][0]["verdict"] == "UNCHECKED"


def test_constants_are_read_without_running_the_script(tmp_path):
    script = tmp_path / "x.py"
    script.write_text(
        'import sys\nENGINE = "lean"\nCLAIM = "7"\nsys.exit("would fail if run")\n',
        encoding="utf-8",
    )
    assert script_constants(script) == {"ENGINE": "lean", "CLAIM": "7"}


EQUATIONS = {
    "slug": "toy",
    "source": "toy.tex",
    "equations": [
        {"number": "1", "line": 3, "latex": "a=b"},
        {"number": "2", "line": 5, "latex": "c=d"},
    ],
}


def _run_with_equations(tmp_path, equations, **constants):
    (tmp_path / "equations.json").write_text(json.dumps(equations), encoding="utf-8")
    verify = tmp_path / "verify"
    (verify / "checks").mkdir(parents=True)
    _check(verify / "checks", "01_x.py", "VERDICT: HOLDS 01_x symbolic | ok", **constants)
    return main([str(verify)])


def test_every_equation_gets_a_claim_entry(tmp_path):
    assert _run_with_equations(tmp_path, EQUATIONS, CLAIM="1") == 0
    data = json.loads((tmp_path / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    schema_check(data)
    assert data["paper"] == "toy"  # equations.json slug wins over the folder name
    assert data["inputs"]["equations_sha256"] is not None
    assert data["inputs"]["attempt"] is None
    assert [(c["claim"], c["verdict"]) for c in data["claims"]] == [("1", "HOLDS"), ("2", "UNCHECKED")]
    assert data["claims"][1]["evidence"]["detail"] == "no check tests this claim"


@pytest.mark.parametrize(
    "constants, message",
    [
        ({"CLAIM": "9"}, "CLAIM '9'"),
        ({"CORRECTS": "9", "CORRECTION": "a=c"}, "CORRECTS '9'"),
        ({"CORRECTS": "1"}, "needs a CORRECTION"),
        ({"CLAIM": "1", "CORRECTS": "1", "CORRECTION": "a=c"}, "both CLAIM and CORRECTS"),
    ],
)
def test_inconsistent_inputs_stop_before_running(tmp_path, capsys, constants, message):
    assert _run_with_equations(tmp_path, EQUATIONS, **constants) == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "verify" / "RESULTS.md").exists()


def test_invalid_equations_stop_before_running(tmp_path, capsys):
    broken = {"slug": "toy", "source": "toy.tex", "equations": [{"number": "1", "latex": "a=b"}]}
    assert _run_with_equations(tmp_path, broken, CLAIM="1") == 2
    assert "line" in capsys.readouterr().err


def test_specimen_checks_flag_the_planted_errors(tmp_path):
    source = REPO / "runs" / "example-oscillator" / "verify" / "checks"
    shutil.copytree(source, tmp_path / "checks")
    assert main([str(tmp_path), "--only", "01_"]) == 0
    assert main([str(tmp_path), "--only", "02_"]) == 1
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "m=k=v=x=1" in text
    assert "| (3) | **FAILS** | counterexample | 02_eq3_paper_energy_step |" in text
    assert main([str(tmp_path), "--only", "03_"]) == 1
    assert "not T" in (tmp_path / "RESULTS.md").read_text(encoding="utf-8")


def test_specimen_run_gives_verdicts_and_a_verified_correction(tmp_path):
    run = tmp_path / "example-oscillator"
    shutil.copytree(REPO / "runs" / "example-oscillator", run)
    assert main([str(run / "verify")]) == 1
    data = json.loads((run / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    schema_check(data)
    claims = {c["claim"]: c for c in data["claims"]}
    assert {n: c["verdict"] for n, c in claims.items()} == {
        "1": "UNCHECKED", "2": "UNCHECKED", "3": "FAILS", "4": "FAILS", "5": "UNCHECKED",
    }
    assert claims["3"]["correction"]["verified"] is True
    assert claims["3"]["correction"]["check_id"] == "01_eq3_energy_step"
    assert claims["4"]["evidence"] == {
        "kind": "symbolic",
        "check_id": "03_eq4_decay_units",
        "engine": "python",
        "script": "verify/checks/03_eq4_decay_units.py",
        "detail": "[b/m] = M0 L0 T-1, not T; 2*m/b is a time",
    }
    assert claims["4"]["correction"]["latex"] == r"\tau=2m/b"
    assert claims["4"]["correction"]["verified"] is True


def test_scratch_attempt_outside_git_records_code_commit_and_inputs(tmp_path):
    """A Verifier scratch folder is not a git repo; the code commit must still be known."""
    attempt = tmp_path / "toy" / "2"
    (attempt / "verify" / "checks").mkdir(parents=True)
    (attempt / "equations.json").write_text(json.dumps(EQUATIONS), encoding="utf-8")
    (attempt / "equations.v1.json").write_text("{}", encoding="utf-8")
    (attempt / "equations.v2.json").write_text("{}", encoding="utf-8")
    (attempt / "conversation.jsonl").write_text(
        json.dumps({"kind": "question"}) + "\n" + json.dumps({"kind": "answer"}) + "\n", encoding="utf-8"
    )
    _check(attempt / "verify" / "checks", "01_x.py", "VERDICT: HOLDS 01_x symbolic | ok", CLAIM="1")
    assert main([str(attempt / "verify")]) == 0
    data = json.loads((attempt / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    schema_check(data)
    assert data["paper"] == "toy"
    assert data["commit"] != "?" and len(data["commit"].split()[0]) >= 7
    assert data["inputs"]["attempt"] == 2
    assert data["inputs"]["equations_versions"] == 2
    assert data["inputs"]["questions"] == 1
    results = (attempt / "verify" / "RESULTS.md").read_text(encoding="utf-8")
    assert "Paper: toy, attempt 2." in results
    assert "2 version(s) received, 1 question(s) asked" in results
