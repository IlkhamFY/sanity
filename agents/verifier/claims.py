"""Load the Reader's equations.json and turn SymPy fields into expressions.

    python claims.py runs/<paper-slug>/equations.json

The file is checked against ``docs/schemas/equations.schema.json`` first.
The ``sympy`` strings come from a language model, so they are never passed
to ``eval`` or ``sympify`` as they are. Each string is parsed with Python's
``ast`` module and rejected unless it uses only arithmetic, numbers,
declared symbols and functions, and a fixed list of SymPy functions.
Only then is it built with ``parse_expr``.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "docs" / "schemas" / "equations.schema.json"

# SymPy names a claim may call or reference without declaring them.
ALLOWED_FUNCTIONS = {
    "sqrt", "exp", "log", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "Abs", "sign", "re", "im", "conjugate",
    "Derivative", "Integral", "Rational", "besselj", "bessely", "gamma",
}
ALLOWED_CONSTANTS = {"pi", "E", "I", "oo"}
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Tuple,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
)
RELATIONS = {"==": sp.Eq, "<": sp.Lt, "<=": sp.Le, ">": sp.Gt, ">=": sp.Ge}


class ClaimError(ValueError):
    """Raised when equations.json or one of its SymPy strings is unusable."""


@dataclass(frozen=True)
class Claim:
    number: str
    line: int
    latex: str
    lhs: sp.Expr | None = None
    rhs: sp.Expr | None = None
    relation: str = "=="
    symbols: dict[str, sp.Symbol] = field(default_factory=dict)

    @property
    def has_sympy(self) -> bool:
        return self.lhs is not None and self.rhs is not None

    def as_relation(self):
        if not self.has_sympy:
            raise ClaimError(f"equation ({self.number}) has no sympy field")
        return RELATIONS[self.relation](self.lhs, self.rhs, evaluate=False)


def validate(data: dict) -> None:
    """Raise ClaimError if ``data`` does not match the equations schema."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(part) for part in exc.absolute_path) or "(root)"
        raise ClaimError(f"equations.json invalid at {where}: {exc.message}") from None


def check_expression(text: str, names: set[str]) -> None:
    """Reject anything but arithmetic over ``names`` and allowed SymPy names."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ClaimError(f"not an expression: {text!r} ({exc.msg})") from None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ClaimError(f"disallowed syntax {type(node).__name__} in {text!r}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ClaimError(f"only numeric literals are allowed in {text!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ClaimError(f"only plain function names may be called in {text!r}")
            if node.keywords:
                raise ClaimError(f"keyword arguments are not allowed in {text!r}")
        if isinstance(node, ast.Name):
            allowed = names | ALLOWED_FUNCTIONS | ALLOWED_CONSTANTS
            if node.id not in allowed:
                raise ClaimError(f"undeclared name {node.id!r} in {text!r}")


def _namespace(spec: dict) -> tuple[dict, dict[str, sp.Symbol]]:
    symbols = {}
    for name, assumptions in spec.get("symbols", {}).items():
        symbols[name] = sp.Symbol(name, **{a: True for a in assumptions})
    functions = {name: sp.Function(name) for name in spec.get("functions", [])}
    overlap = symbols.keys() & functions.keys()
    if overlap:
        raise ClaimError(f"declared as both symbol and function: {sorted(overlap)}")
    local = {**symbols, **functions}
    for name in ALLOWED_FUNCTIONS | ALLOWED_CONSTANTS:
        local[name] = getattr(sp, name)
    return local, symbols


def build_expression(text: str, spec: dict) -> sp.Expr:
    local, _ = _namespace(spec)
    declared = set(spec.get("symbols", {})) | set(spec.get("functions", []))
    check_expression(text, declared)
    # The AST check above is the guard. parse_expr's default globals are kept
    # because its number and symbol transformations need them.
    return parse_expr(text, local_dict=local, evaluate=False)


def parse_claim(entry: dict) -> Claim:
    spec = entry.get("sympy")
    base = {"number": entry["number"], "line": entry["line"], "latex": entry["latex"]}
    if spec is None:
        return Claim(**base)
    _, symbols = _namespace(spec)
    return Claim(
        **base,
        lhs=build_expression(spec["lhs"], spec),
        rhs=build_expression(spec["rhs"], spec),
        relation=spec.get("relation", "=="),
        symbols=symbols,
    )


def load_claims(path: Path) -> list[Claim]:
    """Validate ``equations.json`` and parse every SymPy field in it."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimError(f"cannot read {path}: {exc}") from None
    validate(data)
    claims = []
    for entry in data["equations"]:
        try:
            claims.append(parse_claim(entry))
        except ClaimError as exc:
            raise ClaimError(f"equation ({entry['number']}): {exc}") from None
    return claims


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: claims.py runs/<paper-slug>/equations.json", file=sys.stderr)
        return 2
    try:
        claims = load_claims(Path(args[0]))
    except ClaimError as exc:
        print(f"claims: {exc}", file=sys.stderr)
        return 1
    for claim in claims:
        form = str(claim.as_relation()) if claim.has_sympy else "(no sympy field)"
        print(f"({claim.number:>3})  line {claim.line:<4}  {form}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
