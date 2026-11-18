"""Verdicts, evidence kinds, and how checks combine into one verdict per claim.

A verdict says whether the paper's claim is right. The evidence kind says
how that was decided. Both come from the line an executed script printed;
a hunch is neither. There is no separate judge and no separate ruling: the
claim verdict is the decision.

    HOLDS      proof > symbolic > asymptotic > numerical
    FAILS      refutation > symbolic > asymptotic > counterexample
    UNCHECKED  none (the detail says why)

ERROR is not a verdict about the paper. It means a check script is broken.
"""

from __future__ import annotations

from dataclasses import dataclass

EVIDENCE = {
    "HOLDS": ("proof", "symbolic", "asymptotic", "numerical"),
    "FAILS": ("refutation", "symbolic", "asymptotic", "counterexample"),
    "UNCHECKED": ("none",),
}
VERDICTS = tuple(EVIDENCE)
CHECK_STATUSES = VERDICTS + ("ERROR",)

# Only lean_check.py (not yet written) may report these. Until then a plain
# script that prints them is an ERROR, so no verdict claims a proof it lacks.
LEAN_ONLY = {"proof", "refutation"}


def evidence_problem(verdict: str, kind: str) -> str | None:
    """Why ``verdict`` with evidence ``kind`` is not acceptable, or None."""
    if verdict not in EVIDENCE:
        return f"unknown verdict {verdict!r}"
    if kind not in EVIDENCE[verdict]:
        allowed = ", ".join(EVIDENCE[verdict])
        return f"evidence {kind!r} does not fit {verdict} (allowed: {allowed})"
    if kind in LEAN_ONLY:
        return f"evidence {kind!r} is reserved for lean_check.py, which is not implemented yet"
    return None


def strength(verdict: str, kind: str) -> int:
    """Higher is stronger. Used to pick the evidence shown for a claim."""
    kinds = EVIDENCE.get(verdict, ())
    return len(kinds) - kinds.index(kind) if kind in kinds else 0


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str  # a verdict or ERROR
    evidence: str
    detail: str


@dataclass(frozen=True)
class ClaimVerdict:
    verdict: str
    evidence: str
    check_id: str | None
    detail: str
    conflict: bool = False


def combine(results: list[CheckResult]) -> ClaimVerdict:
    """One verdict for a claim from every check that tests it as printed.

    Checks that disagree (one HOLDS, one FAILS) leave the claim UNCHECKED
    and set ``conflict``: one of the checks is wrong and a person must look.
    A broken check does not settle anything. If nothing settled the claim,
    it stays UNCHECKED.
    """
    if not results:
        return ClaimVerdict("UNCHECKED", "none", None, "no check tests this claim")
    settled = [r for r in results if r.status in {"HOLDS", "FAILS"}]
    statuses = {r.status for r in settled}
    if statuses == {"HOLDS", "FAILS"}:
        ids = ", ".join(f"{r.check_id}={r.status}" for r in settled)
        return ClaimVerdict("UNCHECKED", "none", None, f"checks disagree: {ids}", True)
    if settled:
        best = max(settled, key=lambda r: strength(r.status, r.evidence))
        return ClaimVerdict(best.status, best.evidence, best.check_id, best.detail)
    errors = [r for r in results if r.status == "ERROR"]
    if errors:
        return ClaimVerdict("UNCHECKED", "none", errors[0].check_id, f"check broken: {errors[0].detail}")
    first = results[0]
    return ClaimVerdict("UNCHECKED", "none", first.check_id, first.detail)
