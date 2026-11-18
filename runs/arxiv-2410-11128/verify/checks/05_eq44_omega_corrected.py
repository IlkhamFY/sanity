"""Check 06: corrected equation (4.4) — horizon angular velocity.

Claim: Omega = c*r_minus/(a*(r_plus+r_minus)) equals the horizon value.
Source: correction of arXiv:2410.11128v1, equation (4.4).
Assumptions: r_plus > 0, r_minus > 0, a = sqrt(r_plus*r_minus), c > 0.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "05_eq44_omega_corrected"
ENGINE = "sympy"
CORRECTS = "4.4"
CORRECTION = r"\Omega=\frac{c r_{-}}{a(r_{+}+r_{-})}"

r_plus, r_minus, c = sp.symbols("r_plus r_minus c", positive=True)
a = sp.sqrt(r_plus * r_minus)
horizon = sp.simplify(c * a / (r_plus**2 + a**2))
corrected = sp.simplify(c * r_minus / (a * (r_plus + r_minus)))
difference = sp.simplify(corrected - horizon)
if difference == 0:
    print(
        f"VERDICT: HOLDS {CHECK_ID} symbolic | "
        "simplify(corrected - c*a/(r_plus**2+a**2)) == 0 for a**2=r_plus*r_minus"
    )
else:
    print(
        f"VERDICT: FAILS {CHECK_ID} symbolic | residual {difference}"
    )
