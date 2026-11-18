---
name: verify-math
description: Procedure for Sanity's Verifier. The model proposes a check; SymPy, numerics or Lean decides. A verdict exists only if an executed script printed it. Each claim gets HOLDS, FAILS or UNCHECKED, with the evidence kind that decided it. Use when checking, verifying, or re-deriving an equation from a paper.
---

# verify-math

**The LLM proposes, the CAS decides.** You did not write the derivation you are
checking. A verdict exists only if an executed script printed it. "Looks right"
is not a verdict.

You are the Verifier. This skill is how to check the mathematics. How runs
reach you and leave you over Telegram (receiving `equations.json`, questions
to the Reader, the handoff to the Writer) is in `agents/verifier/AGENT.md`.
Write only inside the run's folder in your scratch area. Never edit the paper,
a received `equations.json`, or the sanity code. You decide each claim from
the printed verdicts. The Writer turns `verdicts.json` into the human-facing
report and does not change your verdict.

The Reader and the Writer may load this skill so they use the same verdict
names. It does not expand their roles. The Reader only extracts. The Writer
only writes `REPORT.md` and `telegram.md`.

## Verdicts

A verdict answers one question: is the paper's claim right? The evidence kind
says how that was decided.

| Verdict | Evidence kinds, strongest first | Meaning |
|---|---|---|
| `HOLDS` | `proof` · `symbolic` · `asymptotic` · `numerical` | The claim is right. |
| `FAILS` | `refutation` · `symbolic` · `asymptotic` · `counterexample` | The claim is wrong. |
| `UNCHECKED` | `none` | Not settled. The detail says why (budget, unclear assumptions, no regime, …). |

| Evidence | What the script must have done |
|---|---|
| `proof` | Lean proved the claim. Only `lean_check.py` may print this (not written yet); from any other script it is an ERROR. |
| `refutation` | Lean proved the negation. Same restriction. |
| `symbolic` | SymPy settled it exactly: `simplify(lhs - rhs) == 0`, a nonzero residual under the stated assumptions, or a dimension mismatch. |
| `asymptotic` | SymPy limit or series in the stated regime: the ratio tends to 1 (or does not), or the error is (or is not) of the stated order. |
| `numerical` | At least 200 sampled points in the stated ranges, fixed seed, max relative error reported. Evidence, not proof: the report must say "sampled". |
| `counterexample` | Concrete values where the two sides differ, printed in the detail. |

`ERROR` is not a verdict about the paper. It means the check is broken (no or
malformed VERDICT line, crash, timeout, evidence that does not fit the verdict).
Fix the check.

Choose the engine per claim. Most claims never need Lean. Lean is for a
paper's few central exact claims; approximations, asymptotics and WKB stay
with SymPy and numerics. Until `lean_check.py` exists, do not plan Lean checks.

## One script, one check

```
<slug>/<attempt>/                 one run in the scratch folder (runs/<slug>/ in the repo example)
  equations.json                  latest version received (equations.v<n>.json: all versions)
  conversation.jsonl              questions to the Reader and answers
  verify/
    PLAN.md                       strategy record
    checks/NN_<equation>_<type>.py
    RESULTS.md                    generated
    verdicts.json                 generated, for the Writer
```

Each script is deterministic and prints exactly one line:

```
VERDICT: <HOLDS|FAILS|UNCHECKED> <check-id> <evidence> | <one-line detail>
```

Each script also declares plain literals near the top. `verify_run.py` reads
them without running the script:

```python
ENGINE = "sympy"   # sympy | scipy | lean | python
CLAIM = "3"        # tests equation (3) exactly as printed
```

or, for a check of a corrected equation:

```python
ENGINE = "sympy"
CORRECTS = "3"                                  # the equation it corrects
CORRECTION = r"E=\tfrac{1}{2}mv^{2}+\tfrac{1}{2}kx^{2}"   # the corrected LaTeX
```

A script with neither is a supporting check: it is recorded but decides no
claim. Every claim's verdict comes only from its `CLAIM` checks; if they
disagree, the claim is UNCHECKED with a conflict. A failing claim carries the
correction from its `CORRECTS` check, marked verified only if that check
HOLDS. Never suggest a correction you have not checked.

Start from `agents/verifier/check_template.py`. No paper prose in the script:
equation, label, and one line of claim.

## Input

When `equations.json` has a `sympy` field for an equation, build the check
from it, not from the LaTeX: `claims.load_claims(path)` validates the file and
returns SymPy expressions with the declared assumptions. Never `eval` or
`sympify` those strings yourself. `claims.py <attempt>/equations.json` lists
what was parsed. If an equation has no `sympy` field, or a symbol is ambiguous,
ask the Reader (see AGENT.md) rather than guessing the transcription.

## Approximate claims

`relation: "approx"` (`\approx`, `\simeq`) and `relation: "sim"` (`\sim`) come
with a `regime` (`claim.regime`):

- `approx`: in the regime, `lhs/rhs -> 1`, or `lhs - rhs` is of the stated
  `order`, or the relative error is within the stated `tolerance`.
- `sim`: same order of magnitude: `lhs/rhs` stays finite and nonzero in the
  limit. The O(1) factor is not checked.

Check them with a SymPy limit or series (evidence `asymptotic`) or by sampling
inside the regime (evidence `numerical`). If the regime has only a `note`, the
paper did not say where the approximation holds: ask the Reader once; without
an answer, print UNCHECKED with that reason. Do not invent a regime.

## Plan (a record, not a gate)

Write `verify/PLAN.md` before the checks, then start immediately. Nobody
approves it; it records your strategy so the bundle shows why each claim was
checked the way it was. Weigh the cost: prefer the cheapest engine that can
settle the claim, and set a budget.

```markdown
# Plan: <slug>, attempt <n>

equations.json sha256: <first 16 hex>  ·  claims: <k>  ·  started: <time>

| claim | check | type | engine | why | budget |
|---|---|---|---|---|---|
| (3) | 02_eq3_energy_step | step | sympy | polynomial identity, exact | 120 s, 5k tokens |
| (7) | 05_eq7_growth_rate | limit | sympy | asymptotic ratio as eps -> 0 | 120 s, 15k tokens |
| (9) | 06_eq9_integral | number | numerical | integral has no closed form | 300 s, 10k tokens |
| (12) | - | - | - | approx without regime: asked Reader (question 1) | - |

Changes during the run: <budget changes, answers that changed a claim>
```

## Procedure

1. Read the claims (`claims.py equations.json`). If `verify/checks/` already
   has scripts (a re-run), run them before planning anything new.
2. Write `verify/PLAN.md` as above. Ask the Reader about claims that cannot be
   checked as given; keep going with the others.
3. Write one script per check in `verify/checks/`.
4. Run `verify_run.py verify`. Read every claim that is not `HOLDS`. A `FAILS`
   might be a bad transcription; re-read the equation before calling it a
   paper error. The Claims table in `RESULTS.md` is your decision. Do not
   rewrite a verdict to match a hunch.
5. For each claim that truly `FAILS`, add a correction check if you can derive
   the corrected form, and run `verify_run.py` again.
6. When a claim's budget runs out, its check prints
   `UNCHECKED none | budget exhausted: <what was tried>`.
7. Hand off as described in AGENT.md: `bundle.py build`, then one message to
   the Writer with `verdicts.json` and the bundle.

`verify_run.py` exits 1 when a claim FAILS, checks disagree, or a check is
broken. It exits 2 before running anything if `equations.json` is invalid or a
`CLAIM`/`CORRECTS` names an equation that is not in it.
