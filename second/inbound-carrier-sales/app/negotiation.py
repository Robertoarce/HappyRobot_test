"""Server-side negotiation policy.

The voice agent never sees MAX_BUY. It reports the carrier's ask and the
round number; this module answers accept / counter / reject and what to say.
Counters start near the loadboard rate and concede toward (but never past)
MAX_BUY across at most three rounds.
"""

from __future__ import annotations

from pydantic import BaseModel

MAX_ROUNDS = 3


class NegotiationDecision(BaseModel):
    decision: str  # accept | counter | reject
    counter_rate: int | None = None
    final_round: bool = False
    message_hint: str


def evaluate(
    carrier_ask: int,
    round_number: int,
    loadboard_rate: int,
    max_buy: int | None,
) -> NegotiationDecision:
    ceiling = max_buy if max_buy is not None else loadboard_rate
    final = round_number >= MAX_ROUNDS

    if carrier_ask <= ceiling:
        return NegotiationDecision(
            decision="accept",
            counter_rate=carrier_ask,
            final_round=final,
            message_hint="Accept the rate and move to booking confirmation.",
        )

    if final:
        return NegotiationDecision(
            decision="reject",
            counter_rate=None,
            final_round=True,
            message_hint=(
                "No agreement after three rounds. Close professionally, "
                "log as failed negotiation, do not transfer."
            ),
        )

    # Concede gradually: each round moves from the posted rate toward the
    # ceiling, never reaching it before the final round.
    fraction = {1: 0.4, 2: 0.75}.get(round_number, 0.9)
    counter = loadboard_rate + int((ceiling - loadboard_rate) * fraction)
    counter = min(counter, ceiling)
    # Round to a natural-sounding $25 step without crossing the ceiling.
    counter = min(ceiling, (counter // 25) * 25)

    return NegotiationDecision(
        decision="counter",
        counter_rate=counter,
        final_round=False,
        message_hint=f"Counter at ${counter}. Do not reveal any ceiling.",
    )
