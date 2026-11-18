"""Check 04: equation (4), corrected — units.

Claim: tau = 2*m/b, from F = -b*v, has dimensions of time.
Source: demo note, corrected equation (4).
Assumptions: b from force over velocity; m is mass; 2 is dimensionless.
Added: 2026-11-18-oscillator. Changed: -.
"""

CHECK_ID = "04_eq4_corrected_decay_units"
ENGINE = "python"  # dimension exponents, no CAS needed
CORRECTS = "4"
CORRECTION = r"\tau=2m/b"

# Exponents (mass, length, time).
force = (1, 1, -2)
velocity = (0, 1, -1)
mass = (1, 0, 0)
time = (0, 0, 1)
damping = tuple(force[i] - velocity[i] for i in range(3))
corrected = tuple(mass[i] - damping[i] for i in range(3))

if corrected == time:
    print(f"VERDICT: HOLDS {CHECK_ID} symbolic | [2m/b] = T")
else:
    print(
        f"VERDICT: FAILS {CHECK_ID} symbolic | "
        f"[2m/b] = M{corrected[0]} L{corrected[1]} T{corrected[2]}, not T"
    )
