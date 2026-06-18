from app.negotiation import evaluate


def test_ask_at_or_below_posted_rate_is_accepted():
    d = evaluate(carrier_ask=1900, round_number=1, loadboard_rate=2150, max_buy=2300)
    assert d.decision == "accept"
    assert d.counter_rate == 1900


def test_above_posted_but_below_ceiling_counters_not_accepts():
    # The bug from the live call: $6000 ask on a $5022 load with headroom under
    # the ceiling must NOT be accepted outright — it must be countered down.
    d = evaluate(carrier_ask=6000, round_number=1, loadboard_rate=5022, max_buy=6500)
    assert d.decision == "counter"
    assert d.counter_rate < 6000  # strictly below the ask — captures savings
    assert d.counter_rate >= 5022  # never below the posted rate


def test_counter_anchors_near_posted_rate_on_first_round():
    d = evaluate(carrier_ask=6000, round_number=1, loadboard_rate=5022, max_buy=6500)
    midpoint = (5022 + 6000) // 2
    assert d.counter_rate < midpoint  # closer to posted than to the ask


def test_counter_never_exceeds_ceiling():
    for rnd in (1, 2):
        d = evaluate(carrier_ask=2600, round_number=rnd, loadboard_rate=2150, max_buy=2300)
        assert d.decision == "counter"
        assert d.counter_rate is not None and d.counter_rate <= 2300


def test_final_round_accepts_when_within_ceiling():
    d = evaluate(carrier_ask=6000, round_number=3, loadboard_rate=5022, max_buy=6500)
    assert d.decision == "accept"
    assert d.counter_rate == 6000
    assert d.final_round is True


def test_round_three_above_ceiling_rejects():
    d = evaluate(carrier_ask=2600, round_number=3, loadboard_rate=2150, max_buy=2300)
    assert d.decision == "reject"
    assert d.final_round is True


def test_missing_max_buy_falls_back_to_loadboard_rate():
    # No ceiling info → never pay above the posted rate; counters stay <= posted.
    d = evaluate(carrier_ask=2200, round_number=1, loadboard_rate=2150, max_buy=None)
    assert d.decision == "counter"
    assert d.counter_rate <= 2150


def test_decision_payload_never_contains_max_buy():
    d = evaluate(carrier_ask=2600, round_number=1, loadboard_rate=2150, max_buy=2300)
    assert "max_buy" not in d.model_dump()
