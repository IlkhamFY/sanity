# Plan: oscillator note

Stage: example.
Scope: equations (3) and (4) of the demo note. Example data, not a published paper.

The Verifier did not write this derivation. This plan is approved for the specimen
scripts already in `verify/checks/`. A new run stops here until a person approves
the rows below. Checks are written only after that, and only inside this `verify/`
directory. The ruling comes from the printed verdict. There is no separate judge.

| id | equation | type | engine | action |
|---|---|---|---|---|
| 01_eq3_energy_step | (3) corrected | step | SymPy | new |
| 02_eq3_paper_energy_step | (3) as printed | step | SymPy | new |
| 03_eq4_decay_units | (4) | units | SymPy | new |

Check 01 checks the corrected form of (3) (`CORRECTS = "3"`), so the report can
give a verified correction. A Lean check would be a later script; only
`lean_check.py` may report evidence `proof` or `refutation`.
