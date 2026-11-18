"""Check 02: equation (3) as printed — step.

Claim: the printed energy (1/2)*m*v**2 + k*x**2 equals the integral of m*v dv + k*x dx.
Source: demo note, equation (3).
Assumptions: m, k, v, x positive.
Added: 2026-11-18-oscillator. Changed: -.
"""

import sympy as sp

CHECK_ID = "02_eq3_paper_energy_step"
ENGINE = "sympy"
CLAIM = "3"
m, k, v, x = sp.symbols("m k v x", positive=True)
printed = sp.Rational(1, 2) * m * v**2 + k * x**2
integral = sp.integrate(m * v, v) + sp.integrate(k * x, x)
difference = sp.simplify(printed - integral)
if difference == 0:
    print(f"VERDICT: VERIFIED {CHECK_ID} | symbolic: simplify(lhs - rhs) == 0")
else:
    point = {m: 1, k: 1, v: 1, x: 1}
    print(
        "VERDICT: FAILED "
        f"{CHECK_ID} | at m=k=v=x=1: printed {printed.subs(point)}, "
        f"integral {integral.subs(point)}, gap {difference}"
    )
