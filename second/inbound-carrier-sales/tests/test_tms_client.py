import pytest

from app.tms_client import TmsClient, TmsCommandError, TmsUnavailableError

from .fake_tms import TOKEN, FakeTms


@pytest.fixture()
def server():
    srv = FakeTms().start()
    yield srv
    srv.stop()


def make_client(server, **overrides) -> TmsClient:
    defaults = dict(
        host="127.0.0.1",
        port=server.port,
        auth_token=TOKEN,
        timeout=1.0,
        max_retries=3,
        backoff_base=0.05,
    )
    defaults.update(overrides)
    return TmsClient(**defaults)


def test_debug_echo_roundtrip(server):
    echo = make_client(server).debug_echo("hello")
    assert echo["MSG"] == "hello"
    assert echo["AUTH"] == "OK"


def test_query_parses_records_and_strips_padding(server):
    records = make_client(server).load_query(ORIG_STATE="GA", EQTYPE="DRY_VAN")
    assert len(records) == 1
    rec = records[0]
    assert rec["ORIG_CITY"] == "Atlanta"  # right-padding stripped
    assert rec["EQTYPE"] == "DRY_VAN"
    assert rec["RATE"] == "0002150"


def test_empty_result_is_not_an_error(server):
    assert make_client(server).load_query(ORIG_STATE="ZZ") == []


def test_load_get_unknown_load_raises_command_error(server):
    with pytest.raises(TmsCommandError) as exc:
        make_client(server).load_get("LD9999999999")
    assert exc.value.code == "UNKNOWN_LOAD"


def test_bad_auth_not_retried(server):
    client = make_client(server, auth_token="wrong")
    with pytest.raises(TmsCommandError) as exc:
        client.debug_echo()
    assert exc.value.code == "AUTH_FAILED"
    assert len(server.requests) == 1  # semantic errors must not be retried


def test_timeout_then_recovers(server):
    server.behaviors = ["timeout", "ok"]
    records = make_client(server).load_query(ORIG_STATE="GA")
    assert len(records) == 1


def test_partial_response_then_recovers(server):
    server.behaviors = ["partial", "ok"]
    records = make_client(server).load_query(ORIG_STATE="GA")
    assert len(records) == 1


def test_malformed_response_then_recovers(server):
    server.behaviors = ["malformed", "ok"]
    records = make_client(server).load_query(ORIG_STATE="GA")
    assert len(records) == 1


def test_delayed_close_does_not_block(server):
    server.behaviors = ["ok_delayed_close"]
    records = make_client(server).load_query(ORIG_STATE="GA")
    assert len(records) == 1  # we stop at END, not at connection close


def test_all_retries_exhausted_raises_unavailable(server):
    server.behaviors = ["timeout", "timeout", "timeout"]
    with pytest.raises(TmsUnavailableError):
        make_client(server).load_query(ORIG_STATE="GA")


def test_booking_success(server):
    rec = make_client(server).load_book("LD0000045821", "872144", 2200)
    assert rec["STATUS"] == "BOOKED"
    assert rec["BOOKING_REF"].startswith("BR")


def test_invalid_rate_raises(server):
    with pytest.raises(TmsCommandError) as exc:
        make_client(server).load_book("LD0000045821", "872144", 0)
    assert exc.value.code == "INVALID_RATE"
