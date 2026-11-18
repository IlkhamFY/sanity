"""Run every saved check and write RESULTS.md and verdicts.json.

    python verify_run.py [VERIFY_DIR] [--only PATTERN] [--timeout SECONDS]
                         [--snapshot RUN_DIR]

Each script in VERIFY_DIR/checks prints one line:

    VERDICT: <Lean-PROVED|VERIFIED|VERIFIED-NUMERICALLY|FAILED|UNCHECKED> <id> | <detail>

and declares, as top-level string constants that are read without running
the script:

    ENGINE = "sympy"   # sympy | scipy | lean | python
    CLAIM = "3"        # equation number it tests as printed; None if supporting

If the run directory has an equations.json, it is validated first and every
CLAIM must name one of its equations.

Lean-PROVED is Sanity's strongest verdict. FAILED, a missing verdict, or more
than one verdict exits 1. UNCHECKED does not. An invalid equations.json or an
unknown CLAIM exits 2 before any check runs. No model is called.
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
from rule import decide

VERDICTS = (
    "Lean-PROVED",
    "VERIFIED",
    "VERIFIED-NUMERICALLY",
    "FAILED",
    "UNCHECKED",
    "ERROR",
)
VERDICT_LINE = re.compile(
    r"^VERDICT:\s*(Lean-PROVED|VERIFIED-NUMERICALLY|VERIFIED|FAILED|UNCHECKED)"
    r"\s+(\S+)\s*\|?\s*(.*)$",
    re.M,
)
FAILURES = {"FAILED", "ERROR"}
ENGINES = {"sympy", "scipy", "lean", "python"}


@dataclass(frozen=True)
class Row:
    check_id: str
    verdict: str
    engine: str
    claim: str | None
    seconds: float
    script: str
    detail: str

    @property
    def ruling(self):
        """Ruling on a paper claim, or None for a supporting check."""
        return None if self.claim is None else decide(self.verdict)


def parse_verdict(text: str):
    found = VERDICT_LINE.findall(text)
    if len(found) != 1:
        return None
    name, check_id, detail = found[0]
    return name, check_id, detail.strip()


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


def script_engine(constants: dict) -> str:
    engine = constants.get("ENGINE")
    return engine if engine in ENGINES else "unspecified"


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


def check_claims(run_dir: Path, scripts: list[Path]) -> str | None:
    """Validate equations.json, if present, and every CLAIM. Returns an error."""
    equations = run_dir / "equations.json"
    if not equations.is_file():
        return None
    try:
        numbers = {claim.number for claim in load_claims(equations)}
    except ClaimError as exc:
        return str(exc)
    for script in scripts:
        claim = script_constants(script).get("CLAIM")
        if claim is not None and claim not in numbers:
            return f"{script.name}: CLAIM {claim!r} is not an equation in equations.json"
    return None


def run_one(script: Path, root: Path, timeout: int) -> Row:
    constants = script_constants(script)
    engine = script_engine(constants)
    claim = constants.get("CLAIM")
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
    parsed = parse_verdict(output)
    if parsed is None:
        detail = "timed out" if code == 124 else f"no single VERDICT line, exit {code}"
        if output.strip() and code != 124:
            detail += ": " + output.strip().splitlines()[-1][:150]
        return Row(script.name, "ERROR", engine, claim, seconds, script.name, detail)
    name, check_id, detail = parsed
    return Row(check_id, name, engine, claim, seconds, script.name, detail.replace("|", "/"))


def count(rows: list[Row]) -> dict[str, int]:
    return {name: sum(row.verdict == name for row in rows) for name in VERDICTS}


def write_results(verify_dir: Path, rows: list[Row], commit: str, now: datetime.datetime) -> Path:
    counts = count(rows)
    lines = [
        "# Verification results (generated by verify_run; do not edit)",
        "",
        f"Run: {now:%Y-%m-%d %H:%M}. Project commit: {commit}.",
        "",
        " · ".join(f"{name}: {counts[name]}" for name in VERDICTS),
        "",
        "| check | claim | verdict | engine | time | script | detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        claim = f"({row.claim})" if row.claim is not None else "supporting"
        lines.append(
            f"| {row.check_id} | {claim} | **{row.verdict}** | {row.engine} | "
            f"{row.seconds:.1f}s | `checks/{row.script}` | {row.detail} |"
        )
    lines.extend(
        [
            "",
            "## Rulings",
            "",
            "The Verifier confirms or rejects each paper claim from the verdict column only.",
            "Supporting checks (no claim) get no ruling.",
            "Lean-verified is set only when the verdict is Lean-PROVED.",
            "",
            "| check | claim | verdict | ruling | lean-verified |",
            "|---|---|---|---|---|",
        ]
    )
    for row in rows:
        ruling = row.ruling
        if ruling is None:
            continue
        lean = "yes" if ruling.lean_verified else "no"
        lines.append(f"| {row.check_id} | ({row.claim}) | {row.verdict} | {ruling.decision} | {lean} |")
    lines.append("")
    destination = verify_dir / "RESULTS.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def write_verdicts(verify_dir: Path, rows: list[Row], commit: str, now: datetime.datetime) -> Path:
    data = {
        "paper": verify_dir.parent.name,
        "generated_at": now.isoformat(timespec="seconds"),
        "commit": commit,
        "counts": count(rows),
        "verdicts": [
            {
                "check_id": row.check_id,
                "claim": row.claim,
                "verdict": row.verdict,
                "ruling": None if row.ruling is None else row.ruling.decision,
                "engine": row.engine,
                "script": f"{verify_dir.name}/checks/{row.script}",
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
    problem = check_claims(root, scripts)
    if problem:
        print(f"verify_run: {problem}", file=sys.stderr)
        return 2
    timeout = int(options["--timeout"])
    rows = []
    for script in scripts:
        row = run_one(script, root, timeout)
        rows.append(row)
        print(f"{row.verdict:22} {row.check_id:32} {row.seconds:>5.1f}s  {row.detail[:90]}")
    commit = project_commit(root)
    now = datetime.datetime.now()
    results = write_results(verify_dir, rows, commit, now)
    verdicts = write_verdicts(verify_dir, rows, commit, now)
    snapshot = options["--snapshot"]
    if snapshot:
        folder = Path(snapshot)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(results, folder / "RESULTS.md")
        shutil.copyfile(verdicts, folder / "verdicts.json")
    print(f"\n{count(rows)}  ->  {results}, {verdicts.name}")
    failed = sum(row.verdict in FAILURES for row in rows)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
