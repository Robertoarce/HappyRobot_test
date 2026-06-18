"""Translate raw TMS records (upper-case fixed-width strings) into clean JSON."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


def _to_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value.lstrip("0") or "0")
    except ValueError:
        return None


def _to_dt(value: str | None) -> str | None:
    # TMS datetimes are YYYYMMDDHHMMSS.
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return None


class LoadSummary(BaseModel):
    load_id: str
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    destination_zip: str | None = None
    pickup_datetime: str | None = None
    equipment_type: str | None = None
    loadboard_rate: int | None = None
    miles: int | None = None
    status: str | None = None


class LoadDetail(LoadSummary):
    delivery_datetime: str | None = None
    weight: int | None = None
    commodity_type: str | None = None
    num_of_pieces: int | None = None
    dimensions: str | None = None
    notes: str | None = None
    # MAX_BUY is intentionally NOT exposed on any response model.


def load_summary_from_record(rec: dict[str, str]) -> LoadSummary:
    return LoadSummary(**_common_fields(rec))


def load_detail_from_record(rec: dict[str, str]) -> LoadDetail:
    return LoadDetail(
        **_common_fields(rec),
        delivery_datetime=_to_dt(rec.get("DELIVERY_DT")),
        weight=_to_int(rec.get("WEIGHT")),
        commodity_type=rec.get("COMMODITY"),
        num_of_pieces=_to_int(rec.get("PIECES")),
        dimensions=rec.get("DIMS"),
        notes=rec.get("NOTES"),
    )


def max_buy_from_record(rec: dict[str, str]) -> int | None:
    """MAX_BUY is only present on tokens flagged for it; never serialized out."""
    return _to_int(rec.get("MAX_BUY"))


def _common_fields(rec: dict[str, str]) -> dict:
    return dict(
        load_id=rec.get("LOAD_ID", ""),
        origin_city=rec.get("ORIG_CITY"),
        origin_state=rec.get("ORIG_STATE"),
        origin_zip=rec.get("ORIG_ZIP"),
        destination_city=rec.get("DEST_CITY"),
        destination_state=rec.get("DEST_STATE"),
        destination_zip=rec.get("DEST_ZIP"),
        pickup_datetime=_to_dt(rec.get("PICKUP_DT")),
        equipment_type=rec.get("EQTYPE"),
        loadboard_rate=_to_int(rec.get("RATE")),
        miles=_to_int(rec.get("MILES")),
        status=rec.get("STATUS"),
    )
