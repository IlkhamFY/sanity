"""Turn Verifier rows into a report and a short Telegram summary.

The verdict string is copied. This module has no path that rewrites it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportRow:
    equation: str
    line: int
    wrong_latex: str
    corrected_latex: str
    verdict: str
    check_id: str
    script: str
    effect: str
    detail: str


def render_report(slug: str, title: str, rows: list[ReportRow], standing: list[str]) -> str:
    lines = [
        f"# Report: {slug}",
        "",
        title,
        "",
        "The Writer does not change a verdict. Each verdict below is the word printed by the check script and recorded in `verify/RESULTS.md`.",
        "",
    ]
    for row in rows:
        effect = _effect_sentence(row.effect)
        lines.extend(
            [
                f"## Equation ({row.equation}), line {row.line}",
                "",
                f"Verdict: **{row.verdict}** (`{row.check_id}`).",
                "",
                effect,
                "",
                "Wrong:",
                "",
                f"`{row.wrong_latex}`",
                "",
                "Corrected:",
                "",
                f"`{row.corrected_latex}`",
                "",
                f"Evidence: [`{row.script}`]({row.script}). {row.detail}",
                "",
            ]
        )
    lines.extend(["## Suggested correction for the authors", ""])
    if not rows:
        lines.append("No correction. Nothing in this run was confirmed.")
    else:
        for row in rows:
            if row.verdict not in {"FAILED", "Lean-PROVED"}:
                continue
            lines.append(
                f"- Equation ({row.equation}): replace `{row.wrong_latex}` with `{row.corrected_latex}`."
            )
    lines.extend(["", "## Also checked", ""])
    if standing:
        lines.append("These statements stand. Their flags are rejected:")
        lines.append("")
        for item in standing:
            lines.append(f"- {item}")
    else:
        lines.append("No separate passing check.")
    lines.append("")
    return "\n".join(lines)


def render_telegram(slug: str, rows: list[ReportRow]) -> str:
    confirmed = [row for row in rows if row.verdict in {"FAILED", "Lean-PROVED"}]
    lines = [f"{slug}: {len(confirmed)} confirmed flag(s).", ""]
    for row in confirmed:
        kind = "propagates" if row.effect == "propagates" else "typo"
        lines.append(
            f"({row.equation}) {row.verdict} — {kind}. See `{row.script}`."
        )
    lines.extend(["", f"Report: runs/{slug}/REPORT.md", ""])
    return "\n".join(lines)


def _effect_sentence(effect: str) -> str:
    if effect == "propagates":
        return "This is an error that propagates. Later steps that reuse the quantity inherit it."
    if effect == "typo":
        return "This is a paper typo. It is local: it does not rewrite the other checked equations."
    return "The Verifier recorded no propagation note for this row."
