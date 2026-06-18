from app.fmcsa import parse_carrier


def _payload(**carrier):
    return {"content": [{"carrier": carrier}]}


def test_eligible_carrier_surfaces_registered_phone():
    out = parse_carrier(
        _payload(
            allowedToOperate="Y",
            statusCode="A",
            legalName="SCHNEIDER NATIONAL CARRIERS INC",
            dotNumber=264184,
            telephone="9205551234",
        )
    )
    assert out["eligible"] is True
    assert out["carrier_name"] == "SCHNEIDER NATIONAL CARRIERS INC"
    assert out["registered_phone"] == "9205551234"


def test_phone_falls_back_to_phyphone():
    out = parse_carrier(_payload(allowedToOperate="Y", statusCode="A", phyPhone="3125550000"))
    assert out["registered_phone"] == "3125550000"


def test_missing_phone_is_none_not_error():
    out = parse_carrier(_payload(allowedToOperate="Y", statusCode="A"))
    assert out["registered_phone"] is None


def test_empty_content_is_not_found():
    out = parse_carrier({"content": []})
    assert out["eligible"] is False
    assert out["reason"] == "MC number not found"


def test_out_of_service_is_ineligible():
    out = parse_carrier(
        _payload(allowedToOperate="Y", statusCode="A", oosDate="2024-01-01", telephone="5551234567")
    )
    assert out["eligible"] is False
    assert out["reason"] == "Carrier is out of service"
