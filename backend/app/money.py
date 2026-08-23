"""Pure unit-conversion helpers — see docs/assumptions.md's unit conventions
(1 rupee = 100 paise, 1 paise = 1000 milli-paise).

Exists because hand-typing a converted integer is exactly how a 100x unit bug gets
into the codebase and sits there until someone checks the arithmetic: an earlier
version of `COST_PER_CONTACT_ATTEMPT_MILLI_PAISE` was hand-computed as `115` for
₹0.115 — off by 100x, since 11.5 paise is 11,500 milli-paise, not 115. Money constants
get defined by calling these functions now, not by typing the answer.
"""
from __future__ import annotations


def rupees_to_paise(rupees: float) -> float:
    return rupees * 100


def paise_to_milli_paise(paise: float) -> int:
    return round(paise * 1000)


def rupees_to_milli_paise(rupees: float) -> int:
    return paise_to_milli_paise(rupees_to_paise(rupees))


def milli_paise_to_paise(milli_paise: int) -> float:
    return milli_paise / 1000


def paise_to_rupees(paise: float) -> float:
    return paise / 100


def milli_paise_to_rupees(milli_paise: int) -> float:
    return paise_to_rupees(milli_paise_to_paise(milli_paise))
