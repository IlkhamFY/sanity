---
name: verify-math
description: Procedure for Sanity's Verifier. The model proposes a check; SymPy or Lean decides. A verdict exists only if an executed script printed it. The Verifier also confirms or rejects each flag from that verdict. Use when checking, verifying, or re-deriving an equation from a paper.
---

# verify-math

**The LLM proposes, the CAS decides.** You did not write the derivation you are
checking. A verdict exists only if an executed script printed it. "Looks right"
is not a verdict.

You are the Verifier. Write only inside `runs/<paper-slug>/verify/`. Never edit
the paper, `equations.json`, the site, the Reader, or the Writer's files.
Confirm or reject each flag from the printed verdict. Do not hand the flag to
another agent. Report the fix in `RESULTS.md`; the Writer turns that into the
human-facing report and does not change your verdict.

The Reader and the Writer may load this skill so they use the same verdict
names. It does not expand their roles. The Reader only extracts. The Writer
only writes `REPORT.md` and `telegram.md`.

## Verdicts

| Verdict | Meaning | Evidence |
|---|---|---|
| `Lean-PROVED` | Lean accepted the claim. Strongest. The flag is confirmed and Lean-verified. | This process ran Lean on the statement and it succeeded. |
| `VERIFIED` | Holds symbolically. The flag is rejected. | `simplify(lhs - rhs) == 0`, assumptions stated in the script. |
| `VERIFIED-NUMERICALLY` | Holds where simplification stalls. The flag is rejected. | At least 200 random points in the stated ranges, max error reported. Fixed seed. |
| `FAILED` | Does not hold. The flag is confirmed. | A concrete counterexample: values, or dimensions, of both sides. |
| `UNCHECKED` | Could not be checked. The ruling stays open. | The reason, in the same line. |

SymPy screens every equation. Lean is only for a flagged step. There is no
second computer-algebra system in this verifier.

## One script, one equation

```
runs/<paper-slug>/verify/
  checks/NN_<equation>_<type>.py
  PLAN.md
  RESULTS.md          generated
  verdicts.json       generated, for the Writer
```

Each script is deterministic and prints exactly one line:

```
VERDICT: <verdict> <check-id> | <one-line detail>
```

Each script also declares two plain literals near the top. `verify_run.py`
reads them without running the script:

```python
ENGINE = "sympy"   # sympy | scipy | lean | python
CLAIM = "3"        # equation number tested as printed; None for a supporting check
```

Only a check with a `CLAIM` gets a ruling. A supporting check (for example the
corrected form of a wrong equation) records its verdict but rules on nothing.

Start from `agents/verifier/check_template.py`. No paper prose in the script:
equation, label, and one line of claim.

## Input

When `equations.json` has a `sympy` field for an equation, build the check
from it, not from the LaTeX: `claims.load_claims(path)` validates the file and
returns SymPy expressions with the declared assumptions. Never `eval` or
`sympify` those strings yourself. `python3 agents/verifier/claims.py
runs/<paper-slug>/equations.json` lists what was parsed.

## Procedure

1. Read `runs/<paper-slug>/status.json`. Act only when `stage` is `verifier`.
   If it is not, stop.
2. If `checks/` already has scripts, run them before planning anything new.
3. Write `PLAN.md`: one row per check (id, equation, type, engine).
   Stop until a person approves it.
4. After approval, add or change scripts only in `checks/`.
5. Run `python3 agents/verifier/verify_run.py runs/<paper-slug>/verify`.
   Read every line that is not `VERIFIED` or `Lean-PROVED`. A `FAILED` script
   might be a bad transcription; re-read the equation before calling it a
   paper error. The Rulings table in `RESULTS.md` is your decision. Do not
   rewrite a verdict to match a hunch.
6. Leave the paper and `equations.json` untouched. Set `stage` to `writer`,
   commit, push, and post `@<writer-bot> runs/<paper-slug> ready`.

`verify_run.py` exits 1 when any check fails, errors, or prints no verdict. It
exits 2 before running anything if `equations.json` is invalid or a `CLAIM`
names an equation that is not in it.
