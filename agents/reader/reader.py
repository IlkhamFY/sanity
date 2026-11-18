"""Reader agent.

Input is a PDF or a LaTeX source. Output is each displayed equation with
the number printed in the paper and the source line it came from.

The Verifier never opens the file. It only sees this list. Extraction is
not implemented in the skeleton.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Equation:
    number: str
    line: int
    latex: str


def extract_equations(source_path: str) -> list[Equation]:
    """Extract displayed equations. Stubbed in this skeleton."""
    raise NotImplementedError(
        f"Reader extraction is a stub (source: {source_path}). "
        "Write Equation values to runs/<paper-slug>/equations.json."
    )
