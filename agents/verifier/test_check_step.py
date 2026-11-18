"""The SymPy screen accepts a true energy integral and rejects a planted one."""

import sympy as sp

from check_step import (
    TIME,
    derived_energy,
    e_folding_time,
    energy_gap,
    energy_rate_on_shell,
    paper_decay_time,
    paper_energy,
)


def test_integral_is_half_mv2_plus_half_kx2():
    m, k, v, x = sp.symbols("m k v x", positive=True)
    energy = derived_energy(m, k, v, x)
    expected = sp.Rational(1, 2) * m * v**2 + sp.Rational(1, 2) * k * x**2
    assert sp.simplify(energy - expected) == 0


def test_planted_dropped_half_is_flagged():
    m, k, v, x = sp.symbols("m k v x", positive=True)
    gap = energy_gap(m, k, v, x)
    assert gap != 0
    assert sp.simplify(gap - sp.Rational(1, 2) * k * x**2) == 0
    assert sp.simplify(paper_energy(m, k, v, x) - derived_energy(m, k, v, x)) != 0


def test_corrected_energy_is_constant_on_shell():
    assert energy_rate_on_shell() == 0


def test_decay_time_has_the_wrong_dimensions():
    assert paper_decay_time() == (0, 0, -1)
    assert paper_decay_time() != TIME
    assert e_folding_time() == TIME
