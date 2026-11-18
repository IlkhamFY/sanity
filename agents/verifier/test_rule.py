"""Rulings follow the printed verdict and nothing else."""

from rule import decide


def test_failed_is_confirmed_without_lean():
    ruling = decide("FAILED")
    assert ruling.verdict == "FAILED"
    assert ruling.decision == "confirmed"
    assert ruling.lean_verified is False


def test_lean_proved_is_confirmed_and_lean_verified():
    ruling = decide("Lean-PROVED")
    assert ruling.decision == "confirmed"
    assert ruling.lean_verified is True


def test_symbolic_and_numeric_passes_reject_the_flag():
    assert decide("VERIFIED").decision == "rejected"
    assert decide("VERIFIED-NUMERICALLY").decision == "rejected"
    assert decide("VERIFIED").lean_verified is False


def test_unchecked_and_error_stay_open():
    assert decide("UNCHECKED").decision == "open"
    assert decide("ERROR").decision == "open"
    assert decide("UNCHECKED").lean_verified is False
