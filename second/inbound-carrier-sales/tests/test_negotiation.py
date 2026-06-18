from app.negotiation import evaluate


def test_ask_at_or_below_ceiling_is_accepted():
    d = evaluate(carrier_ask=1900, round_number=1, loadboard_rate=2150, max_buy=1950)
    assert d.decision == "accept"


def test_counter_never_exceeds_ceiling():
    for rnd in (1, 2):
        d = evaluate(carrier_ask=2600, round_number=rnd, loadboard_rate=2150, max_buy=2300)
        assert d.decision == "counter"
        assert d.counter_rate is not None and d.counter_rate <= 2300


def test_round_three_without_agreement_rejects():
    d = evaluate(carrier_ask=2600, round_number=3, loadboard_rate=2150, max_buy=2300)
    assert d.decision == "reject"
    assert d.final_round is True


def test_missing_max_buy_falls_back_to_loadboard_rate():
    d = evaluate(carrier_ask=2200, round_number=1, loadboard_rate=2150, max_buy=None)
    assert d.decision == "counter"
    assert d.counter_rate <= 2150


def test_decision_payload_never_contains_max_buy():
    d = evaluate(carrier_ask=2600, round_number=1, loadboard_rate=2150, max_buy=2300)
    assert "max_buy" not in d.model_dump()
