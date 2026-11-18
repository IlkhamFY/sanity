"""Check 07: equation (4.5) — entropy in energy and angular momentum.

Claim: S = k*A/(4*l_p**2) with A = 4*pi*(r_plus**2+a**2) equals the printed S(E,J).
Source: arXiv:2410.11128v1, equation (4.5), line 652.
Assumptions: c, hbar, G, k, M, J positive; E = M*c**2; l_p**2 = hbar*G/c**3;
R_S = 2*G*M/c**2; a = J/(M*c); r_plus is the outer root of Delta = 0;
lam = 4*pi*G*k/(c**5*hbar); zeta = c**5/G.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "07_eq45_entropy"
ENGINE = "sympy"
CLAIM = "4.5"

c, hbar, G, k, M, J = sp.symbols("c hbar G k M J", positive=True)
R_S = 2 * G * M / c**2
a = J / (M * c)
r_plus = (R_S + sp.sqrt(R_S**2 - 4 * a**2)) / 2
area = 4 * sp.pi * (r_plus**2 + a**2)
entropy = sp.simplify(k * area / (4 * (hbar * G / c**3)))
energy = M * c**2
entropy_e = sp.simplify(entropy.subs(M, energy / c**2))
lam = 4 * sp.pi * G * k / (c**5 * hbar)
zeta = c**5 / G
printed = lam / 2 * (energy**2 + sp.sqrt(energy**4 - zeta**2 * J**2))
difference = sp.simplify(entropy_e - printed.subs(M, energy / c**2))
if difference == 0:
    print(
        f"VERDICT: HOLDS {CHECK_ID} symbolic | "
        "area law equals lam/2*(E**2+sqrt(E**4-zeta**2*J**2)) for E=M*c**2"
    )
else:
    print(f"VERDICT: FAILS {CHECK_ID} symbolic | residual {difference}")
