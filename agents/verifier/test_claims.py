"""equations.json is validated, and SymPy strings are parsed without eval."""

import json
from pathlib import Path

import pytest
import sympy as sp

from claims import ClaimError, build_expression, load_claims, main, parse_claim

REPO = Path(__file__).resolve().parents[2]
SPECIMEN = REPO / "runs" / "example-oscillator" / "equations.json"


def entry(lhs, rhs, symbols, **extra):
    return {
        "number": "1",
        "line": 1,
        "latex": "x",
        "sympy": {"lhs": lhs, "rhs": rhs, "symbols": symbols, **extra},
    }


def test_specimen_loads_with_assumptions():
    claims = {claim.number: claim for claim in load_claims(SPECIMEN)}
    assert set(claims) == {"1", "2", "3", "4", "5"}
    energy = claims["3"]
    assert energy.has_sympy
    m, k, v, x = (energy.symbols[name] for name in "mkvx")
    assert m.is_positive and k.is_positive
    assert sp.simplify(energy.rhs - (m * v**2 / 2 + k * x**2)) == 0
    assert isinstance(claims["1"].as_relation(), sp.Eq)


def test_claim_without_sympy_field_is_allowed():
    claim = parse_claim({"number": "2", "line": 4, "latex": "a=b"})
    assert not claim.has_sympy
    with pytest.raises(ClaimError):
        claim.as_relation()


def test_relation_and_functions():
    claim = parse_claim(
        entry("Derivative(f(t), t)", "0", {"t": ["real"]}, functions=["f"], relation=">=")
    )
    assert isinstance(claim.as_relation(), sp.Ge)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('true')",
        "x.__class__",
        "[x for x in (1,)]",
        "lambda: 1",
        "x[0]",
        "'string'",
        "open(x)",
        "x^2",
        "sqrt(x, evaluate=False)",
    ],
)
def test_unsafe_or_unsupported_syntax_is_rejected(text):
    with pytest.raises(ClaimError):
        build_expression(text, {"symbols": {"x": []}})


def test_undeclared_symbol_is_rejected():
    with pytest.raises(ClaimError, match="undeclared name 'y'"):
        build_expression("x + y", {"symbols": {"x": []}})


def test_symbol_and_function_with_the_same_name_is_rejected():
    with pytest.raises(ClaimError, match="both symbol and function"):
        build_expression("x", {"symbols": {"x": []}, "functions": ["x"]})


def test_schema_rejects_unknown_assumption(tmp_path):
    bad = {
        "slug": "toy",
        "source": "toy.tex",
        "equations": [entry("x", "1", {"x": ["happy"]})],
    }
    path = tmp_path / "equations.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ClaimError, match="equations.json invalid"):
        load_claims(path)


def test_cli_lists_claims(capsys):
    assert main([str(SPECIMEN)]) == 0
    out = capsys.readouterr().out
    assert "Eq(E, " in out and "line 17" in out
