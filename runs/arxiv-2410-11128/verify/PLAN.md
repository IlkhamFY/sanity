# Plan: arxiv-2410-11128, attempt 1

equations.json sha256: c9ae1846c5e1804c  ·  claims: 8  ·  started: 2026-11-18

Source: arXiv:2410.11128v1, Avramov, Dimov, Radomirov, Rashkov, Vetsov,
"Black Holes and Thermogeometric Optimization". Equations are numbered as in
the v1 PDF. Line numbers are from the v1 `main.tex`. Only the Kerr block
around Eq. (4.4) is in this attempt.

Ground truth for the correction, quoted from the authors' comment on
arXiv:2410.11128v4 (the comment is not on v2; v2's comment is about accretion
and the text): "corrected typo in Eq. (4.4) for the angular velocity:
Ω = c r_+ / (a (r_+ + r_-)) becomes Ω = c r_- / (a (r_+ + r_-))".
The check does not assume that comment. It derives the horizon angular
velocity from the metric in Eq. (4.1).

| claim | check | type | engine | why | budget |
|---|---|---|---|---|---|
| (4.1) | 01_eq41_metric | definition | python | Kerr metric as stated; Einstein equation not checked | - |
| (4.2) | 02_eq42_definitions | definition | python | names for Σ, Δ, a, a_*, R_S | - |
| (4.3) | 03_eq43_horizons | step | sympy | r_± are the roots of Δ = 0 | 120 s, 5k tokens |
| (4.4) | 04_eq44_omega | step | sympy | Ω clause vs null Killing vector on the horizon | 120 s, 5k tokens |
| (4.4) corrected | 05_eq44_omega_corrected | step | sympy | corrected Ω vs the same horizon value | 120 s, 5k tokens |
| supporting | 06_eq44_nat_lean | step | lean | cleared denominators over Nat; no reals in this Lean | 3 compiles, 30k tokens |
| (4.5) | 07_eq45_entropy | step | sympy | area law plus E = M c^2 against the printed S(E,J) | 120 s, 5k tokens |
| (4.6) | 08_eq46_temperature | step | sympy | T = (∂S/∂E)^{-1} against the printed closed form | 120 s, 5k tokens |
| (4.7) | 09_eq47_omega_ej | step | sympy | Ω = −T (∂S/∂J) against the printed closed form | 120 s, 5k tokens |
| (4.9) | 10_eq49_nonextremal | step | sympy | E^2 > ζ J against a_* < 1 | 120 s, 5k tokens |

Estimate: about 12 min (one Lean proof, the rest SymPy, plus the failing claim).
No question to the Reader. Eq. (4.8) is not in this attempt.

Changes during the run: `verify_run.py` finished in a few seconds. Eq. (4.7)
also matches the horizon angular velocity once r₊ > r₋ is used to drop the
square root. Lean proved only the Nat form; the correction verdict is the
SymPy one.
