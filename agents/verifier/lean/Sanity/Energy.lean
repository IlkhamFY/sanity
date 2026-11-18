/-
Second-tier check for a dropped factor of one half.

SymPy integrates `m v dv + k x dx = 0` to `(1/2) m v² + (1/2) k x²`.
The paper claims `(1/2) m v² + k x²`.

Clear the denominator. Write `n = k x²`.
The true potential contributes `n` after doubling.
The paper potential contributes `2 n` after doubling.
Those are not equal when `n` is positive, so the paper step is false.

This file uses the Lean prelude only. A paper-scale verifier would state
the same claim in Mathlib over the reals. Mathlib is not a dependency,
and it should not be built in CI.
-/

namespace Sanity.Energy

/-- The paper potential is twice the integrated potential, cleared of the factor 1/2. -/
theorem paper_potential_drops_a_half (k x : Int) (hk : 0 < k) (hx : 0 < x) :
    2 * (k * x * x) ≠ k * x * x := by
  intro h
  -- `k * x * x` is positive, so it cannot equal twice itself.
  have hxx : 0 < x * x := Int.mul_pos hx hx
  have hn : 0 < k * (x * x) := Int.mul_pos hk hxx
  have : 0 < k * x * x := by simpa [Int.mul_assoc] using hn
  omega

end Sanity.Energy
