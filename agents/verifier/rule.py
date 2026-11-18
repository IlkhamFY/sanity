"""Confirm or reject a flag from an executed verdict.

The Verifier does this itself. There is no separate judge. The only inputs
are the verdict a script printed and, when that verdict is Lean-PROVED, the
fact that Lean accepted the statement. A hunch is not a ruling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ruling:
    verdict: str
    decision: str
    lean_verified: bool


def decide(verdict: str) -> Ruling:
    """Map one printed verdict to a ruling.

    ``confirmed`` means the flag stands. ``rejected`` means the flag is
    rejected and the checked statement stands. ``open`` means the script
    did not settle it. ``lean_verified`` is true only for ``Lean-PROVED``.
    """
    if verdict == "Lean-PROVED":
        return Ruling(verdict, "confirmed", True)
    if verdict == "FAILED":
        return Ruling(verdict, "confirmed", False)
    if verdict in {"VERIFIED", "VERIFIED-NUMERICALLY"}:
        return Ruling(verdict, "rejected", False)
    return Ruling(verdict, "open", False)
