# Plan: example-oscillator

Example data from the site demo, not a published paper. This is a strategy
record, not an approval gate: a Verifier writes it and starts checking.

claims: 5 · checked: (3), (4) · not checked: (1), (2), (5) (kept as UNCHECKED to show the case)

| claim | check | type | engine | why | budget |
|---|---|---|---|---|---|
| (3) | 02_eq3_paper_energy_step | step | sympy | integrate m v dv + k x dx and compare exactly | 120 s, 5k tokens |
| (3) corrected | 01_eq3_energy_step | step | sympy | correction check (`CORRECTS = "3"`) | 120 s, 5k tokens |
| (4) | 03_eq4_decay_units | units | python | dimension exponents, no CAS needed | 120 s, 2k tokens |
| (4) corrected | 04_eq4_corrected_decay_units | units | python | correction check (`CORRECTS = "4"`) | 120 s, 2k tokens |

No Lean check: evidence `proof` or `refutation` may only come from
`lean_check.py`, which does not exist yet.
