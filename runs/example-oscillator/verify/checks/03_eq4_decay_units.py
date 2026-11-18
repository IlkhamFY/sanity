"""Check 03: equation (4) — units.

Claim: tau = b/m, from F = -b*v, has dimensions of time.
Source: demo note, equation (4).
Assumptions: b from force over velocity; m is mass.
Added: 2026-11-18-oscillator. Changed: -.
"""

CHECK_ID = "03_eq4_decay_units"
ENGINE = "python"  # dimension exponents, no CAS needed
CLAIM = "4"

# Exponents (mass, length, time).
force = (1, 1, -2)
velocity = (0, 1, -1)
mass = (1, 0, 0)
time = (0, 0, 1)
damping = tuple(force[i] - velocity[i] for i in range(3))
claimed = tuple(damping[i] - mass[i] for i in range(3))

if claimed == time:
    print(f"VERDICT: HOLDS {CHECK_ID} symbolic | [b/m] = T")
else:
    print(
        "VERDICT: FAILS "
        f"{CHECK_ID} symbolic | [b/m] = M{claimed[0]} L{claimed[1]} T{claimed[2]}, not T; "
        "2*m/b is a time"
    )
