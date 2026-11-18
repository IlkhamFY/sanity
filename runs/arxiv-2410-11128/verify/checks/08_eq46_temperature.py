"""Check 08: equation (4.6) — temperature from the entropy.

Claim: (dS/dE)**(-1) at fixed J equals the printed closed form.
Source: arXiv:2410.11128v1, equation (4.6), line 654.
Assumptions: En, J, lam, zeta positive and En**4 > zeta**2 * J**2.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "08_eq46_temperature"
ENGINE = "sympy"
CLAIM = "4.6"

En, J, lam, zeta = sp.symbols("En J lam zeta", positive=True)
entropy = lam / 2 * (En**2 + sp.sqrt(En**4 - zeta**2 * J**2))
from_derivative = sp.simplify(1 / sp.diff(entropy, En))
printed = sp.sqrt(En**4 - zeta**2 * J**2) / (
    lam * En * (En**2 + sp.sqrt(En**4 - zeta**2 * J**2))
)
difference = sp.simplify(from_derivative - printed)
if difference == 0:
    print(
        f"VERDICT: HOLDS {CHECK_ID} symbolic | "
        "simplify(1/diff(S,E) - printed T) == 0"
    )
else:
    print(f"VERDICT: FAILS {CHECK_ID} symbolic | residual {difference}")
