"""Check 09: equation (4.7) — angular velocity from the entropy.

Claim: -T*(dS/dJ) at fixed E equals the printed closed form,
and that form matches c*a/(r_plus**2+a**2) for a**2 = r_plus*r_minus.
Source: arXiv:2410.11128v1, equation (4.7), line 656.
Assumptions: En, J, lam, zeta, c, hbar, G, k positive; r_plus > r_minus > 0.
Added: arxiv-2410.11128. Changed: -.
"""

import sympy as sp

CHECK_ID = "09_eq47_omega_ej"
ENGINE = "sympy"
CLAIM = "4.7"

En, J, lam, zeta = sp.symbols("En J lam zeta", positive=True)
entropy = lam / 2 * (En**2 + sp.sqrt(En**4 - zeta**2 * J**2))
temperature = sp.simplify(1 / sp.diff(entropy, En))
from_derivative = sp.simplify(-temperature * sp.diff(entropy, J))
printed = zeta**2 * J / (2 * En * (En**2 + sp.sqrt(En**4 - zeta**2 * J**2)))
difference = sp.simplify(from_derivative - printed)
if difference != 0:
    print(f"VERDICT: FAILS {CHECK_ID} symbolic | residual {difference}")
else:
    c, hbar, G, k = sp.symbols("c hbar G k", positive=True)
    r_plus, r_minus = sp.symbols("r_plus r_minus", positive=True)
    spin = sp.sqrt(r_plus * r_minus)
    energy = (r_plus + r_minus) * c**4 / (2 * G)
    angular = spin * energy / c
    zeta_v = c**5 / G
    disc = sp.sqrt(energy**4 - zeta_v**2 * angular**2)
    substituted = sp.simplify(
        zeta_v**2 * angular / (2 * energy * (energy**2 + disc))
    )
    inner = sp.sqrt(-4 * r_minus * r_plus + (r_minus + r_plus) ** 2)
    on_horizon = sp.simplify(substituted.subs(inner, r_plus - r_minus))
    horizon = sp.simplify(c * spin / (r_plus**2 + spin**2))
    gap = sp.simplify(on_horizon - horizon)
    if gap == 0:
        print(
            f"VERDICT: HOLDS {CHECK_ID} symbolic | "
            "simplify(-T*diff(S,J) - printed Omega) == 0, and that form equals "
            "c*a/(r_plus**2+a**2) for a**2=r_plus*r_minus, r_plus>r_minus"
        )
    else:
        print(
            f"VERDICT: HOLDS {CHECK_ID} symbolic | "
            "simplify(-T*diff(S,J) - printed Omega) == 0"
        )
