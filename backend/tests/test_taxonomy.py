import pytest

from app.taxonomy import HARD, SOFT, TECHNICAL, UNKNOWN, classify


def test_known_reason_classifies_correctly():
    info = classify("BAD_REQUEST_ERROR", "insufficient_funds")
    assert info.decline_class == SOFT
    assert info.source == "documented"


def test_harvested_reason_is_tagged_harvested():
    info = classify("BAD_REQUEST_ERROR", "payment_failed")
    assert info.source == "harvested"


def test_risk_reason_sets_risk_flagged():
    info = classify("GATEWAY_ERROR", "payment_risk_check_failed")
    assert info.decline_class == HARD
    assert info.risk_flagged is True


def test_unrecognized_reason_is_unknown_not_a_silent_technical_default():
    """The real production case: an error_reason the taxonomy has never seen. Must
    route to human review (decline_class == UNKNOWN), never silently default to
    TECHNICAL, which would permit fast auto-retry on an unclassified signal."""
    info = classify("BAD_REQUEST_ERROR", "some_reason_razorpay_has_never_documented")
    assert info.decline_class == UNKNOWN
    assert info.source == "unknown"
    assert info.decline_class != TECHNICAL


def test_classify_rejects_none_reason():
    with pytest.raises(ValueError):
        classify("BAD_REQUEST_ERROR", None)
