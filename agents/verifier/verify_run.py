"""Run every saved check and write RESULTS.md and verdicts.json.

    python verify_run.py [VERIFY_DIR] [--only PATTERN] [--timeout SECONDS]
                         [--snapshot RUN_DIR]

Each script in VERIFY_DIR/checks prints exactly one line:

    VERDICT: <HOLDS|FAILS|UNCHECKED> <check-id> <evidence> | <detail>

with evidence from rule.EVIDENCE (e.g. ``HOLDS ... symbolic``, ``FAILS ...
counterexample``, ``UNCHECKED ... none``). Each script also declares plain
top-level literals, read without running it:

    ENGINE = "sympy"         # sympy | scipy | lean | python
    CLAIM = "3"              # tests equation (3) as printed, or
    CORRECTS = "3"           # checks a correction of equation (3), with
    CORRECTION = "E=..."     #   the corrected LaTeX
                             # neither: a supporting check

Every claim gets one verdict (rule.combine). A failing claim gets the
correction from its correction check, marked verified only if that check
HOLDS. If the run directory has an equations.json, it is validated first and
every CLAIM and CORRECTS must name one of its equations.

Exit 1 if a claim FAILS, checks disagree, or a check is broken (ERROR).
Exit 2 before running anything if the inputs are inconsistent. No model is
called.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from claims import ClaimError, load_claims
from rule import CHECK_STATUSES, VERDICTS, CheckResult, ClaimVerdict, combine, evidence_problem

VERDICT_LINE = re.compile(
    r"^VERDICT:\s*(HOLDS|FAILS|UNCHECKED)\s+(\S+)\s+([a-z]+)\s*\|?\s*(.*)$"
)
ANY_VERDICT_LINE = re.compile(r"^VERDICT:.*$", re.M)
ENGINES = {"sympy", "scipy", "lean", "python"}


@dataclass(frozen=True)
class Row:
    check_id: str
    status: str
    evidence: str
    engine: str
    role: str  # claim | correction | supporting
    claim: str | None  # equation number for claim and correction checks
    correction: str | None
    seconds: float
    script: str
    detail: str

    def result(self) -> CheckResult:
        return CheckResult(self.check_id, self.status, self.evidence, self.detail)


def parse_verdict(text: str):
    """(verdict, check_id, evidence, detail), or a string saying what is wrong."""
    lines = ANY_VERDICT_LINE.findall(text)
    if len(lines) != 1:
        return f"expected one VERDICT line, found {len(lines)}"
    match = VERDICT_LINE.match(lines[0].strip())
    if not match:
        return f"malformed VERDICT line: {lines[0].strip()[:120]}"
    verdict, check_id, evidence, detail = match.groups()
    problem = evidence_problem(verdict, evidence)
    if problem:
        return problem
    return verdict, check_id, evidence, detail.strip()


def script_constants(script: Path) -> dict:
    """Top-level ``NAME = "literal"`` assignments, read without executing."""
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return {}
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
            if node.value.value is None or isinstance(node.value.value, str):
                found[target.id] = node.value.value
    return found


def script_role(constants: dict) -> tuple[str, str | None]:
    if constants.get("CLAIM") is not None:
        return "claim", constants["CLAIM"]
    if constants.get("CORRECTS") is not None:
        return "correction", constants["CORRECTS"]
    return "supporting", None


def project_commit(root: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip() or "?"
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        return "?"
    if dirty:
        commit += " (+ uncommitted changes)"
    return commit


def check_scripts(verify_dir: Path, only: str) -> list[Path]:
    checks = verify_dir / "checks"
    scripts = sorted(checks.glob("*.py"))
    return [script for script in scripts if only in script.name]


def check_inputs(run_dir: Path, scripts: list[Path]) -> tuple[list[str] | None, str | None]:
    """Equation numbers from equations.json (None if absent), and an error."""
    numbers = None
    equations = run_dir / "equations.json"
    if equations.is_file():
        try:
            numbers = [claim.number for claim in load_claims(equations)]
        except ClaimError as exc:
            return None, str(exc)
    for script in scripts:
        constants = script_constants(script)
        claim, corrects = constants.get("CLAIM"), constants.get("CORRECTS")
        if claim is not None and corrects is not None:
            return numbers, f"{script.name}: declares both CLAIM and CORRECTS"
        if corrects is not None and not constants.get("CORRECTION"):
            return numbers, f"{script.name}: CORRECTS needs a CORRECTION (the corrected LaTeX)"
        for name, value in (("CLAIM", claim), ("CORRECTS", corrects)):
            if numbers is not None and value is not None and value not in numbers:
                return numbers, f"{script.name}: {name} {value!r} is not an equation in equations.json"
    return numbers, None


def run_one(script: Path, root: Path, timeout: int) -> Row:
    constants = script_constants(script)
    engine = constants.get("ENGINE") if constants.get("ENGINE") in ENGINES else "unspecified"
    role, claim = script_role(constants)
    correction = constants.get("CORRECTION") if role == "correction" else None
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    started = datetime.datetime.now()
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        output = completed.stdout + completed.stderr
        code = completed.returncode
    except subprocess.TimeoutExpired:
        output, code = "", 124
    seconds = round((datetime.datetime.now() - started).total_seconds(), 1)
    base = dict(engine=engine, role=role, claim=claim, correction=correction,
                seconds=seconds, script=script.name)
    parsed = parse_verdict(output) if code != 124 else "timed out"
    if isinstance(parsed, str):
        detail = parsed
        if code not in (0, 124):
            detail += f"; exit {code}"
            if output.strip():
                detail += ": " + output.strip().splitlines()[-1][:150]
        return Row(script.name, "ERROR", "none", detail=detail, **base)
    verdict, check_id, evidence, detail = parsed
    return Row(check_id, verdict, evidence, detail=detail.replace("|", "/"), **base)


def claim_numbers(rows: list[Row], equations: list[str] | None) -> list[str]:
    if equations is not None:
        return equations
    seen = []
    for row in rows:
        if row.claim is not None and row.claim not in seen:
            seen.append(row.claim)
    return seen


def correction_for(number: str, rows: list[Row]) -> dict | None:
    candidates = [row for row in rows if row.role == "correction" and row.claim == number]
    if not candidates:
        return None
    chosen = next((row for row in candidates if row.status == "HOLDS"), candidates[0])
    return {
        "latex": chosen.correction,
        "check_id": chosen.check_id,
        "verified": chosen.status == "HOLDS",
        "evidence": chosen.evidence,
        "detail": chosen.detail,
    }


def judge_claims(rows: list[Row], equations: list[str] | None) -> list[dict]:
    by_id = {row.check_id: row for row in rows}
    claims = []
    for number in claim_numbers(rows, equations):
        tested = [row for row in rows if row.role == "claim" and row.claim == number]
        verdict: ClaimVerdict = combine([row.result() for row in tested])
        source = by_id.get(verdict.check_id) if verdict.check_id else None
        claims.append(
            {
                "claim": number,
                "verdict": verdict.verdict,
                "evidence": {
                    "kind": verdict.evidence,
                    "check_id": verdict.check_id,
                    "engine": source.engine if source else None,
                    "script": f"verify/checks/{source.script}" if source else None,
                    "detail": verdict.detail,
                },
                "conflict": verdict.conflict,
                "correction": correction_for(number, rows) if verdict.verdict == "FAILS" else None,
            }
        )
    return claims


def counts(rows: list[Row], claims: list[dict]) -> dict:
    return {
        "claims": {name: sum(c["verdict"] == name for c in claims) for name in VERDICTS},
        "checks": {name: sum(r.status == name for r in rows) for name in CHECK_STATUSES},
    }


def _cell(text) -> str:
    return "" if text is None else str(text).replace("|", "/")


def write_results(verify_dir: Path, rows: list[Row], claims: list[dict], commit: str,
                  now: datetime.datetime) -> Path:
    tally = counts(rows, claims)
    lines = [
        "# Verification results (generated by verify_run; do not edit)",
        "",
        f"Run: {now:%Y-%m-%d %H:%M}. Project commit: {commit}.",
        "",
        "Claims: " + " · ".join(f"{k}: {v}" for k, v in tally["claims"].items()),
        "",
        "Checks: " + " · ".join(f"{k}: {v}" for k, v in tally["checks"].items()),
        "",
        "## Claims",
        "",
        "One verdict per equation, from the checks that test it as printed.",
        "A correction is verified only if its own check HOLDS.",
        "",
        "| claim | verdict | evidence | check | correction | detail |",
        "|---|---|---|---|---|---|",
    ]
    for claim in claims:
        evidence = claim["evidence"]
        correction = claim["correction"]
        fix = ""
        if correction:
            state = "verified" if correction["verified"] else "NOT verified"
            fix = f"`{_cell(correction['latex'])}` ({state}, {correction['check_id']})"
        verdict = claim["verdict"] + (" (conflict)" if claim["conflict"] else "")
        lines.append(
            f"| ({claim['claim']}) | **{verdict}** | {evidence['kind']} | "
            f"{_cell(evidence['check_id'])} | {fix} | {_cell(evidence['detail'])} |"
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | role | claim | verdict | evidence | engine | time | script | detail |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        claim = f"({row.claim})" if row.claim is not None else ""
        lines.append(
            f"| {row.check_id} | {row.role} | {claim} | **{row.status}** | {row.evidence} | "
            f"{row.engine} | {row.seconds:.1f}s | `checks/{row.script}` | {_cell(row.detail)} |"
        )
    lines.append("")
    destination = verify_dir / "RESULTS.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def write_verdicts(verify_dir: Path, rows: list[Row], claims: list[dict], commit: str,
                   now: datetime.datetime) -> Path:
    data = {
        "paper": verify_dir.parent.name,
        "generated_at": now.isoformat(timespec="seconds"),
        "commit": commit,
        "counts": counts(rows, claims),
        "claims": claims,
        "checks": [
            {
                "check_id": row.check_id,
                "role": row.role,
                "claim": row.claim,
                "verdict": row.status,
                "evidence": row.evidence,
                "engine": row.engine,
                "script": f"verify/checks/{row.script}",
                "detail": row.detail,
                "seconds": row.seconds,
            }
            for row in rows
        ],
    }
    destination = verify_dir / "verdicts.json"
    destination.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    options = {"--only": "", "--timeout": "120", "--snapshot": ""}
    positionals = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in options:
            if index + 1 >= len(args):
                print(f"verify_run: {arg} needs a value", file=sys.stderr)
                return 2
            options[arg] = args[index + 1]
            index += 2
            continue
        if arg.startswith("--"):
            print(f"verify_run: unknown option {arg}", file=sys.stderr)
            return 2
        positionals.append(arg)
        index += 1
    default = Path(__file__).resolve().parent / "verify"
    verify_dir = Path(positionals[0]).resolve() if positionals else default
    scripts = check_scripts(verify_dir, options["--only"])
    if not scripts:
        print(f"verify_run: no checks in {verify_dir / 'checks'}", file=sys.stderr)
        return 2
    root = verify_dir.parent
    equations, problem = check_inputs(root, scripts)
    if problem:
        print(f"verify_run: {problem}", file=sys.stderr)
        return 2
    timeout = int(options["--timeout"])
    rows = []
    for script in scripts:
        row = run_one(script, root, timeout)
        rows.append(row)
        print(f"{row.status:10} {row.evidence:15} {row.check_id:32} {row.seconds:>5.1f}s  {row.detail[:80]}")
    claims = judge_claims(rows, equations)
    commit = project_commit(root)
    now = datetime.datetime.now()
    results = write_results(verify_dir, rows, claims, commit, now)
    verdicts = write_verdicts(verify_dir, rows, claims, commit, now)
    snapshot = options["--snapshot"]
    if snapshot:
        folder = Path(snapshot)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(results, folder / "RESULTS.md")
        shutil.copyfile(verdicts, folder / "verdicts.json")
    tally = counts(rows, claims)
    print(f"\nclaims {tally['claims']}  checks {tally['checks']}  ->  {results}, {verdicts.name}")
    bad = (
        any(row.status == "ERROR" for row in rows)
        or any(claim["verdict"] == "FAILS" or claim["conflict"] for claim in claims)
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
