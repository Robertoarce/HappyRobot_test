"""Server-side negotiation policy.

The voice agent never sees MAX_BUY. It reports the carrier's ask and the round
number; this module answers accept / counter / reject and what to say.

The goal is to pay as little as possible above the posted (loadboard) rate while
never exceeding the hidden ceiling (MAX_BUY). So the policy anchors at the posted
rate and counters *below* the carrier's ask — it does not simply accept any ask
that happens to fall under the ceiling, which would leak margin whenever a
carrier opens just beneath it. We concede upward toward whichever is lower (the
ask or the ceiling) across at most three rounds, then take the deal on the final
round if it is within the ceiling, otherwise walk away.
"""

from __future__ import annotations

from pydantic import BaseModel

MAX_ROUNDS = 3


class NegotiationDecision(BaseModel):
    decision: str  # accept | counter | reject
    counter_rate: int | None = None
    final_round: bool = False
    message_hint: str


def _accept(rate: int, final: bool) -> NegotiationDecision:
    return NegotiationDecision(
        decision="accept",
        counter_rate=rate,
        final_round=final,
        message_hint="Accept the rate and move to booking confirmation.",
    )


def evaluate(
    carrier_ask: int,
    round_number: int,
    loadboard_rate: int,
    max_buy: int | None,
) -> NegotiationDecision:
    ceiling = max_buy if max_buy is not None else loadboard_rate
    final = round_number >= MAX_ROUNDS

    # 1. Carrier is at or below the posted rate — a good deal, take it.
    if carrier_ask <= loadboard_rate:
        return _accept(carrier_ask, final)

    # 2. Last round: take it if it is within the ceiling, otherwise no deal.
    if final:
        if carrier_ask <= ceiling:
            return _accept(carrier_ask, True)
        return NegotiationDecision(
            decision="reject",
            counter_rate=None,
            final_round=True,
            message_hint=(
                "No agreement after three rounds. Close professionally, "
                "log as failed negotiation, do not transfer."
            ),
        )

    # 3. Counter below the ask. Anchor at the posted rate and concede upward
    #    toward whichever is lower — the carrier's ask or the ceiling — so we
    #    never offer more than they asked for and never cross the ceiling.
    target = min(carrier_ask, ceiling)
    fraction = {1: 0.4, 2: 0.75}.get(round_number, 0.9)
    counter = loadboard_rate + int((target - loadboard_rate) * fraction)
    # Round to a natural-sounding $25 step, keep it within [posted, target].
    counter = (counter // 25) * 25
    counter = max(loadboard_rate, min(counter, target))

    return NegotiationDecision(
        decision="counter",
        counter_rate=counter,
        final_round=False,
        message_hint=f"Counter at ${counter}. Do not reveal any ceiling.",
    )
