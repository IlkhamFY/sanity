"""Check 01: equation (4.1) — stated metric.

Claim: nothing to decide. The line is the Kerr metric in Boyer-Lindquist form.
Source: arXiv:2410.11128v1, equation (4.1), line 617.
Assumptions: none used.
Added: arxiv-2410.11128. Changed: -.
"""

CHECK_ID = "01_eq41_metric"
ENGINE = "python"
CLAIM = "4.1"

print(
    f"VERDICT: UNCHECKED {CHECK_ID} none | "
    "stated Kerr metric; the Einstein equation was not checked"
)
