"""Check 01: equation (3), corrected — step.

Claim: integrating m*v dv + k*x dx gives (1/2)*m*v**2 + (1/2)*k*x**2.
Source: demo note, corrected equation (3).
Assumptions: m, k, v, x positive.
Added: 2026-11-18-oscillator. Changed: -.
"""

import sympy as sp

CHECK_ID = "01_eq3_energy_step"
ENGINE = "sympy"
CLAIM = None  # supporting: checks the corrected form, not the printed equation
m, k, v, x = sp.symbols("m k v x", positive=True)
lhs = sp.integrate(m * v, v) + sp.integrate(k * x, x)
rhs = sp.Rational(1, 2) * m * v**2 + sp.Rational(1, 2) * k * x**2
difference = sp.simplify(lhs - rhs)
if difference == 0:
    print(f"VERDICT: VERIFIED {CHECK_ID} | symbolic: simplify(lhs - rhs) == 0")
else:
    print(f"VERDICT: FAILED {CHECK_ID} | residual {difference}")
