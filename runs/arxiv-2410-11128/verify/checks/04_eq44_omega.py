"""Check 04: equation (4.4) as printed — horizon angular velocity.

Claim: the Omega clause equals the angular velocity that makes
k = d_t + Omega d_phi null on the outer horizon of the metric in (4.1).
Source: arXiv:2410.11128v1, equation (4.4), line 636.
Assumptions: r_plus > r_minus > 0, a = sqrt(r_plus*r_minus), c > 0.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "04_eq44_omega"
ENGINE = "sympy"
CLAIM = "4.4"

r, theta, a_s, R_S, c = sp.symbols("r theta a R_S c", positive=True)
sigma = r**2 + a_s**2 * sp.cos(theta) ** 2
g_tt = -(1 - R_S * r / sigma) * c**2
g_tphi = -(R_S * a_s * r * sp.sin(theta) ** 2 / sigma) * c
g_phiphi = (
    r**2 + a_s**2 + R_S * a_s**2 * r * sp.sin(theta) ** 2 / sigma
) * sp.sin(theta) ** 2
omega = sp.symbols("Omega")
null = sp.together(g_tt + 2 * g_tphi * omega + g_phiphi * omega**2)
null_h = null.subs(R_S, (r**2 + a_s**2) / r)
solutions = [sp.simplify(sol) for sol in sp.solve(sp.numer(sp.together(null_h)), omega)]
horizon_r = sp.simplify(c * a_s / (r**2 + a_s**2))
if solutions != [horizon_r]:
    print(
        f"VERDICT: UNCHECKED {CHECK_ID} none | "
        f"horizon root was {solutions}, expected {horizon_r}"
    )
else:
    r_plus, r_minus = sp.symbols("r_plus r_minus", positive=True)
    a = sp.sqrt(r_plus * r_minus)
    horizon = sp.simplify(horizon_r.subs({r: r_plus, a_s: a}))
    printed = sp.simplify(c * r_plus / (a * (r_plus + r_minus)))
    ratio = sp.simplify(printed / horizon)
    point = {r_plus: 2, r_minus: 1, c: 1}
    if ratio == 1:
        print(
            f"VERDICT: HOLDS {CHECK_ID} symbolic | "
            "printed Omega equals c*a/(r_plus**2+a**2) for a**2=r_plus*r_minus"
        )
    else:
        shown_p = sp.simplify(printed.subs(point))
        shown_h = sp.simplify(horizon.subs(point))
        print(
            "VERDICT: FAILS "
            f"{CHECK_ID} counterexample | "
            "at r_plus=2, r_minus=1, a=sqrt(2), c=1: "
            f"printed {shown_p}, horizon {shown_h}, ratio {ratio}"
        )
