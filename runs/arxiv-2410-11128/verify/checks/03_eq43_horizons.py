"""Check 03: equation (4.3) — horizon radii.

Claim: r_pm = (R_S pm sqrt(R_S**2 - 4*a**2))/2 are the roots of Delta = 0.
Source: arXiv:2410.11128v1, equation (4.3), line 630.
Assumptions: R_S > 0, a > 0, R_S**2 > 4*a**2 so both roots are real and positive.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "03_eq43_horizons"
ENGINE = "sympy"
CLAIM = "4.3"

R_S, a = sp.symbols("R_S a", positive=True)
disc = sp.sqrt(R_S**2 - 4 * a**2)
r_plus = (R_S + disc) / 2
r_minus = (R_S - disc) / 2
delta_plus = sp.simplify(sp.expand(r_plus**2 - R_S * r_plus + a**2))
delta_minus = sp.simplify(sp.expand(r_minus**2 - R_S * r_minus + a**2))
sum_roots = sp.simplify(r_plus + r_minus - R_S)
product = sp.simplify(r_plus * r_minus - a**2)
if delta_plus == 0 and delta_minus == 0 and sum_roots == 0 and product == 0:
    print(
        f"VERDICT: HOLDS {CHECK_ID} symbolic | "
        "both roots satisfy Delta=0; r_plus+r_minus=R_S; r_plus*r_minus=a**2"
    )
else:
    print(
        f"VERDICT: FAILS {CHECK_ID} symbolic | "
        f"residuals Delta+={delta_plus}, Delta-={delta_minus}, "
        f"sum={sum_roots}, product={product}"
    )
