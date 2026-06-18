"""REST facade for the HappyRobot voice workflow.

Bridges the platform's webhook tools to the legacy TMS (raw TCP), the FMCSA
verification API, the OTP flow, and the negotiation policy. Every endpoint
requires the X-API-Key header.
"""

from __future__ import annotations

import logging
from functools import partial

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .fmcsa import FmcsaClient
from .models import (
    LoadDetail,
    LoadSummary,
    load_detail_from_record,
    load_summary_from_record,
    max_buy_from_record,
)
from .negotiation import NegotiationDecision, evaluate
from .otp import OtpStore
from .tms_client import TmsClient, TmsCommandError, TmsUnavailableError

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Inbound Carrier Sales Middleware", version="1.0.0")

_otp_store: OtpStore | None = None


def get_otp_store(settings: Settings = Depends(get_settings)) -> OtpStore:
    global _otp_store
    if _otp_store is None:
        _otp_store = OtpStore(settings.otp_ttl_seconds, settings.otp_max_attempts)
    return _otp_store


def require_api_key(
    x_api_key: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid API key")


def get_tms(settings: Settings = Depends(get_settings)) -> TmsClient:
    return TmsClient(
        host=settings.tms_host,
        port=settings.tms_port,
        auth_token=settings.tms_auth_token,
        timeout=settings.tms_timeout_seconds,
        max_retries=settings.tms_max_retries,
    )


async def run_tms(func, *args, **kwargs):
    """The TMS client is blocking; run it off the event loop and map errors."""
    try:
        return await anyio.to_thread.run_sync(partial(func, *args, **kwargs))
    except TmsCommandError as exc:
        # Map known semantic codes to clean HTTP status for the agent.
        # The live server uses NOT_FOUND; the docs sample said UNKNOWN_LOAD.
        status = {
            "NOT_FOUND": 404,
            "UNKNOWN_LOAD": 404,
            "ALREADY_BOOKED": 409,
            "INVALID_RATE": 422,
            "MISSING_FIELD": 422,
        }.get(exc.code, 409)
        raise HTTPException(status_code=status, detail={"code": exc.code, "msg": exc.msg})
    except TmsUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/tms/ping", dependencies=[Depends(require_api_key)])
async def tms_ping(tms: TmsClient = Depends(get_tms)):
    echo = await run_tms(tms.debug_echo, "healthcheck")
    return {"connected": True, "echo": echo}


# ----------------------------------------------------------------- carriers

class VerifyCarrierRequest(BaseModel):
    mc_number: str = Field(pattern=r"^\d{4,8}$")


@app.post("/carriers/verify", dependencies=[Depends(require_api_key)])
async def verify_carrier(
    body: VerifyCarrierRequest, settings: Settings = Depends(get_settings)
):
    client = FmcsaClient(settings.fmcsa_base_url, settings.fmcsa_web_key)
    try:
        return await client.verify_mc(body.mc_number)
    except Exception as exc:  # surface as 502 so the agent can apologize/retry
        logging.exception("FMCSA lookup failed")
        raise HTTPException(status_code=502, detail=f"FMCSA lookup failed: {exc}")


# ---------------------------------------------------------------------- OTP

class OtpRequest(BaseModel):
    session_id: str


class OtpVerifyRequest(BaseModel):
    session_id: str
    code: str


@app.post("/otp/request", dependencies=[Depends(require_api_key)])
async def otp_request(body: OtpRequest, store: OtpStore = Depends(get_otp_store)):
    # The code goes only to the workflow's SMS node, never to the agent node.
    return {"code": store.issue(body.session_id)}


@app.post("/otp/verify", dependencies=[Depends(require_api_key)])
async def otp_verify(body: OtpVerifyRequest, store: OtpStore = Depends(get_otp_store)):
    return store.verify(body.session_id, body.code)


# -------------------------------------------------------------------- loads

class LoadSearchRequest(BaseModel):
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    destination_zip: str | None = None
    equipment_type: str | None = None
    pickup_date: str | None = None  # YYYYMMDD
    max_results: int = 5


@app.post("/loads/search", dependencies=[Depends(require_api_key)])
async def search_loads(
    body: LoadSearchRequest, tms: TmsClient = Depends(get_tms)
) -> list[LoadSummary]:
    filters = {
        "ORIG_CITY": body.origin_city,
        "ORIG_STATE": body.origin_state,
        "ORIG_ZIP": body.origin_zip,
        "DEST_CITY": body.destination_city,
        "DEST_STATE": body.destination_state,
        "DEST_ZIP": body.destination_zip,
        "EQTYPE": body.equipment_type,
        "PICKUP_DATE": body.pickup_date,
        "MAX_RESULTS": str(body.max_results),
    }
    filters = {k: v for k, v in filters.items() if v}
    if set(filters) <= {"MAX_RESULTS"}:
        raise HTTPException(status_code=422, detail="at least one search filter required")
    records = await run_tms(tms.load_query, **filters)
    loads = [load_summary_from_record(r) for r in records]
    return [l for l in loads if (l.status or "OPEN").upper() == "OPEN"]


@app.get("/loads/{load_id}", dependencies=[Depends(require_api_key)])
async def get_load(load_id: str, tms: TmsClient = Depends(get_tms)) -> LoadDetail:
    record = await run_tms(tms.load_get, load_id)
    return load_detail_from_record(record)  # MAX_BUY never leaves the server


class BookRequest(BaseModel):
    mc_number: str = Field(pattern=r"^\d{4,8}$")
    agreed_rate: int = Field(gt=0)


@app.post("/loads/{load_id}/book", dependencies=[Depends(require_api_key)])
async def book_load(load_id: str, body: BookRequest, tms: TmsClient = Depends(get_tms)):
    record = await run_tms(tms.load_book, load_id, body.mc_number, body.agreed_rate)
    return {
        "load_id": record.get("LOAD_ID", load_id),
        "booking_reference": record.get("BOOKING_REF"),
        "status": record.get("STATUS"),
        "timestamp": record.get("TIMESTAMP"),
    }


# -------------------------------------------------------------- negotiation

class NegotiationRequest(BaseModel):
    load_id: str
    carrier_ask: int = Field(gt=0)
    round_number: int = Field(ge=1)


@app.post("/negotiate/evaluate", dependencies=[Depends(require_api_key)])
async def negotiate(
    body: NegotiationRequest, tms: TmsClient = Depends(get_tms)
) -> NegotiationDecision:
    record = await run_tms(tms.load_get, body.load_id)
    detail = load_detail_from_record(record)
    if detail.loadboard_rate is None:
        raise HTTPException(status_code=502, detail="load has no posted rate")
    return evaluate(
        carrier_ask=body.carrier_ask,
        round_number=body.round_number,
        loadboard_rate=detail.loadboard_rate,
        max_buy=max_buy_from_record(record),
    )
