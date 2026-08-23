import pytest

from app.money import (
    milli_paise_to_paise,
    milli_paise_to_rupees,
    paise_to_milli_paise,
    paise_to_rupees,
    rupees_to_milli_paise,
    rupees_to_paise,
)


def test_known_value_rupees_to_milli_paise():
    """The exact bug this module exists to prevent: ₹0.115 is 11,500 milli-paise,
    not 115. A hand-typed constant got this wrong by 100x; this pins the correct
    value so it can't silently regress."""
    assert rupees_to_milli_paise(0.115) == 11_500
    assert rupees_to_milli_paise(0.145) == 14_500
    assert rupees_to_milli_paise(1.0) == 100_000


def test_round_trip_rupees_paise_milli_paise():
    for r in (0.115, 0.145, 1.0, 5000.0, 0.01, 83.5):
        milli_paise = rupees_to_milli_paise(r)
        back = milli_paise_to_rupees(milli_paise)
        assert back == pytest.approx(r, abs=1e-9)


def test_intermediate_paise_step_is_correct():
    assert rupees_to_paise(0.115) == pytest.approx(11.5)
    assert paise_to_milli_paise(11.5) == 11_500
    assert milli_paise_to_paise(11_500) == pytest.approx(11.5)
    assert paise_to_rupees(11.5) == pytest.approx(0.115)
