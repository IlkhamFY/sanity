# Lean, second tier

SymPy screens every equation. It is fast and it does not trust the model: algebra, dimensions, limits, special cases.

For a central exact claim, the Verifier may ask an LLM to formalize it as a Lean 4 statement against Mathlib. If Lean proves it, the claim `HOLDS` with evidence `proof`; if Lean proves its negation, it `FAILS` with evidence `refutation`. A Lean run that times out proves nothing: the claim stays `UNCHECKED` unless a refutation or a counterexample is found. Only `lean_check.py` (planned) may report `proof` or `refutation`; `verify_run.py` treats them as an ERROR from any other script. The model does not get the last word.

## This directory

`Sanity/Energy.lean` is a small specimen of that handoff, for the same planted error the SymPy test catches: a harmonic-oscillator energy written with `k x²` instead of `(1/2) k x²`.

The theorem is stated over `Int` and proved with `omega`, so the package does not depend on Mathlib. A real paper would need reals, analysis, and Mathlib. Do not build Mathlib in CI for this skeleton.

The site demo shows this theorem as example data. The Verifier's Lean result is the proof; the Writer's card is the summary.

## Build locally

[elan](https://github.com/leanprover/elan) reads `lean-toolchain` (Lean 4.22.0). From this directory:

```bash
lake build
```

That fetches the Lean compiler on first run. It does not fetch Mathlib. `lake build` should finish on the prelude alone.

Nothing here needs to run in CI.
