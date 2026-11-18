"""Fast SymPy screen for a single derivation step.

This is the check the demo site plants, and the claim formalized in
``agents/verifier/lean``:

* motion ``m x'' = -k x``
* multiplied by velocity, ``m v dv + k x dx = 0``
* the integral is ``(1/2) m v^2 + (1/2) k x^2``
* the paper writes ``(1/2) m v^2 + k x^2`` (a dropped factor of 1/2)

A second helper screens the dimensions of a damping time. SymPy runs on
every equation. Algebraic flags are handed to Lean; this module does not.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

# Mass, length, time exponents.
Dimension = tuple[int, int, int]

MASS: Dimension = (1, 0, 0)
LENGTH: Dimension = (0, 1, 0)
TIME: Dimension = (0, 0, 1)
FORCE: Dimension = (1, 1, -2)
VELOCITY: Dimension = (0, 1, -1)


def _sub(a: Dimension, b: Dimension) -> Dimension:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def derived_energy(m, k, v, x):
    """Integrate ``m v dv + k x dx = 0`` up to a constant.

    ``integrate(m*v, v) + integrate(k*x, x)`` is the conserved energy.
    """
    kinetic = sp.integrate(m * v, v)
    potential = sp.integrate(k * x, x)
    return sp.simplify(kinetic + potential)


def paper_energy(m, k, v, x):
    """Planted error: the potential is written ``k x^2``, not ``(1/2) k x^2``."""
    return sp.Rational(1, 2) * m * v**2 + k * x**2


def energy_gap(m, k, v, x):
    """Claimed energy minus the integral. Zero means the step checks out."""
    return sp.simplify(paper_energy(m, k, v, x) - derived_energy(m, k, v, x))


def energy_rate_on_shell():
    """Time derivative of the corrected energy along ``m x'' + k x = 0``.

    A correct energy is constant, so this expression simplifies to 0.
    """
    t = sp.symbols("t", real=True)
    x = sp.Function("x")
    m, k = sp.symbols("m k", positive=True)
    position = x(t)
    velocity = sp.diff(position, t)
    energy = (
        sp.Rational(1, 2) * m * velocity**2
        + sp.Rational(1, 2) * k * position**2
    )
    rate = sp.diff(energy, t)
    acceleration = -(k / m) * position
    return sp.simplify(rate.subs(sp.diff(position, (t, 2)), acceleration))


def damping_coefficient() -> Dimension:
    """Dimensions of ``b`` in ``F = -b v``."""
    return _sub(FORCE, VELOCITY)


def paper_decay_time() -> Dimension:
    """Dimensions of the planted claim ``tau = b / m``."""
    return _sub(damping_coefficient(), MASS)


def e_folding_time() -> Dimension:
    """Dimensions of ``tau = 2 m / b``. The factor 2 is dimensionless.

    Underdamped amplitude decays as ``exp(-(b / 2m) t)``, so the
    e-folding time is ``2m/b``, which has dimensions of time.
    """
    return _sub(MASS, damping_coefficient())


def format_dimension(dim: Dimension) -> str:
    parts = []
    for name, exp in zip(("M", "L", "T"), dim):
        if exp == 0:
            continue
        parts.append(name if exp == 1 else f"{name}^{exp}")
    return " ".join(parts) if parts else "1"


@dataclass(frozen=True)
class ScreenResult:
    name: str
    ok: bool
    detail: str


def screen_energy() -> ScreenResult:
    m, k, v, x = sp.symbols("m k v x", positive=True)
    gap = energy_gap(m, k, v, x)
    if gap == 0:
        return ScreenResult("energy", True, "integral matches the claim")
    return ScreenResult("energy", False, f"dropped factor: claim - integral = {gap}")


def screen_decay_time() -> ScreenResult:
    claimed = paper_decay_time()
    if claimed == TIME:
        return ScreenResult("decay-time", True, "tau has dimensions of time")
    return ScreenResult(
        "decay-time",
        False,
        f"tau = b/m has dimensions {format_dimension(claimed)}, not T; "
        "e-folding time is 2m/b",
    )


def main() -> None:
    for result in (screen_energy(), screen_decay_time()):
        status = "pass" if result.ok else "flag"
        print(f"{status:4}  {result.name:12}  {result.detail}")


if __name__ == "__main__":
    main()
