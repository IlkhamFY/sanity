"""Claim verdicts follow the printed check verdicts and nothing else."""

from rule import CheckResult, combine, evidence_problem, strength


def result(check_id, status, evidence, detail="d"):
    return CheckResult(check_id, status, evidence, detail)


def test_evidence_must_fit_the_verdict():
    assert evidence_problem("HOLDS", "symbolic") is None
    assert evidence_problem("FAILS", "counterexample") is None
    assert evidence_problem("UNCHECKED", "none") is None
    assert "does not fit" in evidence_problem("HOLDS", "counterexample")
    assert "does not fit" in evidence_problem("UNCHECKED", "symbolic")
    assert "unknown verdict" in evidence_problem("VERIFIED", "symbolic")


def test_lean_evidence_is_reserved_for_lean_check():
    assert "reserved" in evidence_problem("HOLDS", "proof")
    assert "reserved" in evidence_problem("FAILS", "refutation")


def test_strength_orders_evidence():
    assert strength("HOLDS", "proof") > strength("HOLDS", "symbolic") > strength("HOLDS", "numerical")
    assert strength("FAILS", "symbolic") > strength("FAILS", "counterexample")


def test_claim_without_checks_is_unchecked():
    verdict = combine([])
    assert (verdict.verdict, verdict.evidence, verdict.check_id) == ("UNCHECKED", "none", None)


def test_strongest_agreeing_evidence_is_shown():
    verdict = combine([result("a", "HOLDS", "numerical"), result("b", "HOLDS", "symbolic")])
    assert (verdict.verdict, verdict.evidence, verdict.check_id) == ("HOLDS", "symbolic", "b")


def test_disagreeing_checks_leave_the_claim_unchecked():
    verdict = combine([result("a", "HOLDS", "symbolic"), result("b", "FAILS", "counterexample")])
    assert verdict.verdict == "UNCHECKED"
    assert verdict.conflict
    assert "a=HOLDS" in verdict.detail and "b=FAILS" in verdict.detail


def test_a_settled_check_beats_unchecked_and_error():
    verdict = combine([result("a", "UNCHECKED", "none"), result("b", "ERROR", "none"), result("c", "FAILS", "symbolic")])
    assert (verdict.verdict, verdict.check_id) == ("FAILS", "c")


def test_only_a_broken_check_leaves_the_claim_unchecked():
    verdict = combine([result("a", "ERROR", "none", "exit 1")])
    assert verdict.verdict == "UNCHECKED"
    assert "check broken: exit 1" == verdict.detail
