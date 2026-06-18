from app.main import _mask_phone
from app.otp import OtpStore


def test_issue_binds_phone_and_verifies():
    store = OtpStore()
    code = store.issue("sess-1", phone="9205551234")
    # The bound number is recorded for the SMS node, not returned with the code.
    assert store._entries["sess-1"].phone == "9205551234"
    assert store.verify("sess-1", code)["verified"] is True


def test_issue_without_phone_still_works():
    store = OtpStore()
    code = store.issue("sess-2")
    assert store._entries["sess-2"].phone is None
    assert store.verify("sess-2", code)["verified"] is True


def test_wrong_code_decrements_attempts_then_locks():
    store = OtpStore(max_attempts=2)
    store.issue("s", phone="5551234567")
    assert store.verify("s", "000000")["verified"] is False
    last = store.verify("s", "111111")
    assert last["verified"] is False
    assert last["reason"] == "too_many_attempts"


def test_mask_phone_keeps_only_last_four():
    assert _mask_phone("9205551234") == "•••-•••-1234"
    assert _mask_phone("(312) 555-0000") == "•••-•••-0000"
    assert _mask_phone(None) is None
    assert _mask_phone("12") == "•••"
