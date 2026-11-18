"""Check 10: equation (4.9) — non-extremality.

Claim: for positive E, zeta, J, E**2 > zeta*J is the same statement as a_* < 1
when a_* = zeta*J/E**2, which is the paper's specific spin in Eq. (4.8).
Source: arXiv:2410.11128v1, equation (4.9), line 664.
Assumptions: En, zeta, J positive.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "10_eq49_nonextremal"
ENGINE = "sympy"
CLAIM = "4.9"

En, zeta, J = sp.symbols("En zeta J", positive=True)
a_star = zeta * J / En**2
gap = sp.simplify(En**2 * (1 - a_star) - (En**2 - zeta * J))
if gap == 0:
    print(
        f"VERDICT: HOLDS {CHECK_ID} symbolic | "
        "E**2 > zeta*J iff a_*=zeta*J/E**2 < 1, since E**2 > 0"
    )
else:
    print(f"VERDICT: FAILS {CHECK_ID} symbolic | residual {gap}")
