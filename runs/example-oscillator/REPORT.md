# Report: example-oscillator

A spring, missing a half. Example data from `note.tex`, the same note as the site demo. Not a published paper.

The Writer does not change a verdict. Each verdict below is the word printed by the check script and recorded in `verify/RESULTS.md`.

## Equation (3), line 17

Verdict: **FAILED** (`02_eq3_paper_energy_step`). Ruling: confirmed.

This is an error that propagates. The printed energy is the quantity a later step would reuse, and the potential is twice the integral of `k x dx`.

Wrong:

`E=\tfrac{1}{2}mv^{2}+kx^{2}`

Corrected:

`E=\tfrac{1}{2}mv^{2}+\tfrac{1}{2}kx^{2}`

Evidence: [`verify/checks/02_eq3_paper_energy_step.py`](verify/checks/02_eq3_paper_energy_step.py). At m=k=v=x=1 the printed side is 3/2, the integral is 1, and the gap is `k*x**2/2`.

The corrected equation was checked on its own. Verdict: **VERIFIED** (`01_eq3_energy_step`). Ruling: rejected, so that statement stands. Evidence: [`verify/checks/01_eq3_energy_step.py`](verify/checks/01_eq3_energy_step.py).

This run has no `Lean-PROVED` line. The prelude statement for the same gap is `agents/verifier/lean/Sanity/Energy.lean`. It is not a verdict until a script prints one.

## Equation (4), line 22

Verdict: **FAILED** (`03_eq4_decay_units`). Ruling: confirmed.

This is a paper typo. `tau = b/m` does not have dimensions of time. It does not rewrite equation (3).

Wrong:

`\tau=b/m`

Corrected:

`\tau=2m/b`

Evidence: [`verify/checks/03_eq4_decay_units.py`](verify/checks/03_eq4_decay_units.py). `[b/m] = M0 L0 T-1`, not T. `2*m/b` is a time.

## Suggested correction for the authors

- Equation (3), line 17: replace `E=\tfrac{1}{2}mv^{2}+kx^{2}` with `E=\tfrac{1}{2}mv^{2}+\tfrac{1}{2}kx^{2}`.
- Equation (4), line 22: replace `\tau=b/m` with `\tau=2m/b`.

## Also checked

Equations (1), (2), and (5) have no script in this run, so they have no verdict.
