# Report: arxiv-2410-11128

Sanity flags Eq. (4.4) in v1 and proposes the same fix the authors recorded for that equation.

Black Holes and Thermogeometric Optimization, Avramov, Dimov, Radomirov, Rashkov, and Vetsov. This run checks the Kerr block around Eq. (4.4) in [arXiv:2410.11128v1](https://arxiv.org/abs/2410.11128v1). It does not check the rest of the paper.

The authors' comment on [arXiv:2410.11128v4](https://arxiv.org/abs/2410.11128v4) says: corrected typo in Eq. (4.4) for the angular velocity, Ω = c r₊ / (a (r₊ + r₋)) becomes Ω = c r₋ / (a (r₊ + r₋)). That comment is not on v2. v2's comment is about accretion and the text. The checks did not take the comment as an input.

The Writer does not change a verdict. Each verdict below is the word printed by the check script and recorded in `verify/RESULTS.md`.

Of the eight equations in this run, five hold, one fails, and two were not checked.

## Equation (4.4), line 636

Verdict: **FAILS** (`04_eq44_omega`). Evidence: counterexample.

The angular-velocity clause does not match the value that makes ∂ₜ + Ω ∂φ null on the horizon of Eq. (4.1). At r₊ = 2, r₋ = 1, a = √2, c = 1 the printed value is √2/3 and the horizon value is √2/6. The ratio is r₊/r₋, so the two agree only when r₊ = r₋.

Wrong:

`\Omega=\frac{c r_{+}}{a(r_{+}+r_{-})}`

Corrected:

`\Omega=\frac{c r_{-}}{a(r_{+}+r_{-})}`

Evidence: [`verify/checks/04_eq44_omega.py`](verify/checks/04_eq44_omega.py). at r_plus=2, r_minus=1, a=sqrt(2), c=1: printed sqrt(2)/3, horizon sqrt(2)/6, ratio r_plus/r_minus.

The corrected clause was checked on its own. Verdict: **HOLDS** (`05_eq44_omega_corrected`). Evidence: symbolic. simplify(corrected - c*a/(r_plus**2+a**2)) == 0 for a**2=r_plus*r_minus.

A Lean 4.22 check of the same relation with the denominators cleared, over Nat, printed **HOLDS** with evidence proof (`06_eq44_nat_lean`, axioms: none). This Lean has no real numbers, so that file does not replace the SymPy result.

## Suggested correction for the authors

- Equation (4.4), line 636: replace `\Omega=\frac{c r_{+}}{a(r_{+}+r_{-})}` with `\Omega=\frac{c r_{-}}{a(r_{+}+r_{-})}`.

This is the replacement in the v4 comment.

## Also checked

These statements stand:

- (4.3) **HOLDS**, symbolic. Both roots satisfy Δ = 0, r₊ + r₋ = R_S, and r₊ r₋ = a².
- (4.5) **HOLDS**, symbolic. The area law equals the printed S(E, J) for E = M c².
- (4.6) **HOLDS**, symbolic. T = (∂S/∂E)⁻¹ matches the printed closed form.
- (4.7) **HOLDS**, symbolic. Ω = −T (∂S/∂J) matches the printed closed form, and that form equals c a / (r₊² + a²).
- (4.9) **HOLDS**, symbolic. E² > ζ J is the same as a_* < 1 for positive E, ζ, J.

Equations (4.1) and (4.2) are **UNCHECKED**. (4.1) is the stated Kerr metric; the Einstein equation was not checked. (4.2) defines Σ, Δ, a, a_*, and R_S. Eq. (4.8) is not in this run.

In this slice the paper's later formulas for S, T, and Ω(E, J) hold. The horizon angular velocity in Eq. (4.4) of v1 does not.
