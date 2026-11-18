-- Lean check, supporting: the cleared-denominator form of the corrected
-- angular velocity, over Nat. Core Lean has no reals, so this does not
-- by itself prove the real identity. The SymPy correction check does that.
-- Given a*a = rPlus*rMinus, rMinus*rPlus = a*a.
-- CHECK_ID: 06_eq44_nat_lean
-- THEOREM: Sanity.Check.eq44_nat
-- EXPECT: proof

namespace Sanity.Check

theorem eq44_nat (rPlus rMinus a : Nat) (h : a * a = rPlus * rMinus) :
    rMinus * rPlus = a * a := by
  calc
    rMinus * rPlus = rPlus * rMinus := Nat.mul_comm _ _
    _ = a * a := h.symm

end Sanity.Check
