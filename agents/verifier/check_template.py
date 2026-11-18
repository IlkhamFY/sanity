"""Check <NN>: equation (<label>) — <step|limit|units|number>.

Claim: <one line, no paper prose>. Source: <equation label and line>.
Assumptions: <signs, ranges, approximations>.
Added: <run id>. Changed: -.

The model may draft this file. A verdict exists only after the file has been
executed and has printed one VERDICT line. Do not report a verdict from reading.
"""

from __future__ import annotations

import random

import sympy as sp

CHECK_ID = "NN_label_type"
# Read by verify_run without running this file. Keep both as plain literals.
ENGINE = "sympy"  # sympy | scipy | lean | python
CLAIM = None  # equation number tested as printed, e.g. "3"; None for a supporting check
NUMERIC_POINTS = 200
NUMERIC_TOLERANCE = sp.Float("1e-8")

random.seed(0)

# Replace these. Declare assumptions the way the paper states them.
m, k, v, x = sp.symbols("m k v x", positive=True)
lhs = None
rhs = None


def verdict(name: str, detail: str) -> None:
    print(f"VERDICT: {name} {CHECK_ID} | {detail}")


def sample_relative_error(lhs, rhs, symbols, ranges):
    """Worst relative error of ``lhs - rhs`` over ``NUMERIC_POINTS`` samples.

    ``ranges`` maps each symbol to ``(low, high)``. The seed is fixed.
    Returns ``(worst, point)`` with the point as a dict of floats.
    """
    if len(ranges) != len(symbols):
        raise ValueError("every symbol needs a range")
    random.seed(0)
    difference = sp.lambdify(symbols, lhs - rhs, "math")
    left = sp.lambdify(symbols, lhs, "math")
    worst = 0.0
    worst_point = None
    for _ in range(NUMERIC_POINTS):
        point = {symbol: random.uniform(*ranges[symbol]) for symbol in symbols}
        values = [point[symbol] for symbol in symbols]
        scale = max(abs(left(*values)), 1e-30)
        error = abs(difference(*values)) / scale
        if worst_point is None or error > worst:
            worst = error
            worst_point = point
    return worst, worst_point


def main() -> int:
    if lhs is None or rhs is None:
        verdict("UNCHECKED", "template not filled in")
        return 2
    difference = sp.simplify(sp.expand(lhs - rhs))
    if difference == 0:
        verdict("VERIFIED", "symbolic: simplify(lhs - rhs) == 0")
        return 0
    ranges = {m: (0.1, 10), k: (0.1, 10), v: (0.1, 10), x: (0.1, 10)}
    worst, point = sample_relative_error(lhs, rhs, (m, k, v, x), ranges)
    shown = {str(symbol): f"{value:.6g}" for symbol, value in point.items()}
    if worst < float(NUMERIC_TOLERANCE):
        verdict(
            "VERIFIED-NUMERICALLY",
            f"{NUMERIC_POINTS} points, max rel err {worst:.3g}",
        )
        return 0
    verdict("FAILED", f"max rel err {worst:.3g} at {shown}; residual {difference}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
