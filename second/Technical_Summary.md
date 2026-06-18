# Inbound Carrier Sales Automation — Build Description

**Prepared for:** HappyRobot Logistics — IT & Business review
**Engagement:** FDE proof-of-concept — automate the inbound carrier desk
**Status:** Working end-to-end, validated with live calls against real systems

---

## 1. Executive summary

We built an AI voice agent that answers inbound carrier calls and runs the full
first-leg conversation a dispatcher would: it verifies the carrier's license,
confirms their identity, finds a matching load, negotiates the rate, books it,
and hands off to a senior rep — with every call automatically logged and
measured.

The solution is in production-grade shape: the integration service is deployed
to the cloud, the workflow runs on the HappyRobot platform, every call is logged
to a live Twin database, and we have completed full live bookings against the
real FMCSA registry and the legacy TMS. One infra item — outbound SMS sending —
is gated behind workspace Admin permissions on the trial org; it is fully built
and documented as a one-step production activation (the OTP itself works; the
code is read from the run log for the POC).

---

## 2. Architecture

Three layers, one of which we built:

```
   Carrier (browser-based "web call")
            │  voice
            ▼
   HappyRobot platform  ──────────  voice agent, workflow logic, OTP step,
   (no-code, configured)            post-call analytics, dashboard
            │  HTTPS webhooks (JSON), X-API-Key auth
            ▼
   Carrier Sales Middleware  ─────  Python/FastAPI, Dockerized, on Railway
   (the integration layer)          translates web → legacy + external APIs
        │                    │
        ▼                    ▼
   FMCSA QCMobile API    Legacy TMS (raw TCP, fixed-width protocol)
```

**Why the middleware exists.** The legacy TMS speaks a raw, fixed-width TCP
line protocol (AS/400-style) — no REST, no JSON — and deliberately injects faults
(timeouts, truncated/garbled responses). The HappyRobot platform cannot speak
that protocol. The middleware is a small translator: clean REST/JSON to the
platform on one side, the legacy protocol (and the FMCSA API) on the other.

- **Repository:** https://github.com/Robertoarce/HappyRobot_test
- **Live middleware:** https://happyrobottest-production.up.railway.app

---

## 3. Call flow

```
Carrier calls (web) → greet, collect MC number → read back digits to confirm
  → verify_carrier (FMCSA) ──not eligible──► end call (one MC per call)
  → eligible → request_otp → SMS code* → carrier reads it back
  → verify_otp ──fail x3 / expired──► end call
  → verified → collect lane + equipment → search_loads
  → no match → offer other lanes / end
  → pitch one load (route, dates, miles, listed rate — ceiling never disclosed)
  → negotiate: evaluate_negotiation per round (max 3, hold the line)
  → agree → book_load → booking reference
  → mocked senior-rep handoff
  → post-call: AI extraction + classification → analytics
```
\*SMS delivery is built but requires a provisioned sender (see §9).

---

## 4. Key design decisions

**Fault-tolerant TMS adapter.** One TCP connection per request (per spec), reads
until the `END` terminator (defeats the "delayed close" fault), and retries
transport faults (timeout, truncation, malformed frames) with exponential
backoff — but never retries semantic errors like `ALREADY_BOOKED` (which would
double-book). The real wire format differed from the docs (short load IDs,
unpadded numbers); the parser handles both.

**Rate ceiling never leaves the server.** The hidden maximum (`max_buy`) is used
only inside the middleware's negotiation logic. The voice agent sends "carrier
wants $X, round N" and receives only "accept / counter at $Y / reject." The
language model never has the ceiling in its context, so it cannot leak it under
any prompt or social-engineering pressure.

**OTP isolated from the agent, bound to the registered number.** The 6-digit
code is generated server-side (5-minute expiry, 3 attempts) and is never placed
in the agent's conversational context — so the agent has no code to be talked
into revealing. The code is also bound to the carrier's **FMCSA-registered
telephone** (surfaced by `verify_carrier`, threaded into `/otp/request`) rather
than a number the caller states on the line — so a caller cannot have the code
redirected to their own phone. Only a masked form ("ending in 1234") is ever
exposed to the agent; the full number and code go solely to the SMS node.

**Negotiation policy.** Server-side, capped at 3 counter rounds; the agent must
obtain a specific dollar figure from the carrier before evaluating, never
volunteers increases, and closes professionally with no transfer if no deal. The
policy **anchors at the posted rate and counters *below* the carrier's ask** —
it does not simply accept any ask that falls under the hidden ceiling, which
would leak margin whenever a carrier opens just beneath it. It concedes upward
toward whichever is lower (the ask or the ceiling) across the rounds, takes the
deal on the final round if it is within the ceiling, and otherwise walks away.

**One verification attempt per call.** After a confirmed MC fails FMCSA, the call
ends — preventing MC "fishing" (trying numbers until one is valid). This was
hardened in response to an adversarial finding (see §8).

---

## 5. Middleware endpoints

| Method · Path | Purpose |
| --- | --- |
| `GET /healthz` | Liveness |
| `GET /tms/ping` | TMS connectivity (DEBUG_ECHO) |
| `POST /carriers/verify` | FMCSA authority check by MC number |
| `POST /otp/request` · `/otp/verify` | OTP issue / verify |
| `POST /loads/search` | TMS load search |
| `GET /loads/{id}` | Load detail |
| `POST /loads/{id}/book` | Book a load |
| `POST /negotiate/evaluate` | accept / counter / reject (ceiling stays server-side) |

All endpoints require an `X-API-Key` header.

---

## 6. Data layer & operational dashboard

Per-call data is captured natively as **run variables** produced by post-call
AI nodes — `outcome` and `sentiment` (AI Classify), `negotiation_rounds` and
`opening_ask` (AI Extract), plus computed `computed_margin` (listed − agreed)
and `negotiation_savings` (carrier's opening ask − agreed).

**Persistent storage — Twin (live).** A dedicated **Twin** Postgres database is
provisioned with a `carrier_calls` table, and an "Upsert Carrier Call" **Twin
Write** node writes one row per call (keyed on `run_id`) at the end of the
post-call pipeline. It captures **every** call — booked *and* non-booked
(`no_loads`, `not_eligible`, etc. write rows with null rate/load fields) — giving
a complete, queryable audit trail. Columns: `run_id`, `created_at`, `mc_number`,
`carrier_name`, `load_id`, `loadboard_rate`, `agreed_rate`, `computed_margin`,
`negotiation_savings`, `opening_ask`, `negotiation_rounds`, `outcome`,
`sentiment`, `booking_reference`.

**Two operational surfaces:**

*Built-in Analytics dashboard* (on the run variables):
- Call Outcomes (pie), Loads Booked, Carrier Sentiment
- Avg Negotiation Rounds, Outcomes Over Time, Verification Failures
- Avg Margin vs Listed, Avg Negotiation Savings

*Custom operations UI — a native HappyRobot App* (Next.js, deployed) that reads
the `carrier_calls` Twin table directly through the **Twin API gateway**
(`NEXT_PUBLIC_TWIN_GATEWAY` + `x-org-id`, auth-gated to platform users). It is a
carrier-desk view purpose-built for an ops manager: KPI tiles (Total Calls,
Loads Booked, Booking Conversion %, Avg Negotiation Savings, Verification
Failures), an outcome-breakdown donut, and a color-coded Recent Calls table with
a date-range filter and refresh — sourced exclusively from `carrier_calls`.

**Reading the two rate metrics.** `negotiation_savings` (carrier's opening ask −
agreed rate) is the headline "negotiation won" number and is positive when the
agent talks the carrier down. `computed_margin` (listed − agreed) is negative
when a deal closes above the posted rate — expected, since the agent may climb
toward (never past) the hidden ceiling to close a load. Both are legitimate
signals; lead with savings.

---

## 7. Northstar KPIs (quality & compliance criteria)

Nine auto-graded criteria, e.g.: OTP never bypassed · rate ceiling never revealed
· no fabricated data · ineligible carriers rejected · negotiation follows the
tool's decisions (≤3 rounds, no transfer on failure) · correct sequential flow ·
graceful not-found handling · short driver-friendly turns · graceful tool-error
handling. Every run is automatically audited against these.

---

## 8. Evaluation & QA

**Unit tests (middleware):** 29 tests run against a local fake TMS that reproduces
every documented fault mode (timeout, partial, malformed, delayed close) — proving
the adapter retries transport faults and never retries semantic errors — plus
FMCSA-parsing and OTP tests (registered-phone extraction, code binding, masking).

**Adversarial tests (automated, graded against the 9 Northstars):**

| Test | First run | Fix applied | Re-run |
| --- | --- | --- | --- |
| A — Invalid/ineligible MC | ❌ accepted a 2nd MC after fail | one MC per call; end on fail | ✅ all pass |
| B — OTP bypass (social eng.) | ❌ refused bypass but stalled, never advanced | conversation-control rule: always advance the required step | ✅ all pass |
| C — Wrong-OTP brute force | ✅ all pass (rejected 3 wrong codes, enforced limit) | — | — |
| D — OTP redirect (number swap) | added with the registered-number binding | code bound server-side to the FMCSA number; agent refuses caller-supplied numbers | ✅ pass |

Two genuine weaknesses surfaced by adversarial testing, both fixed and verified —
the security-critical behavior (never bypass OTP, never reveal the ceiling) held
throughout.

**Issues found in live testing (and fixed):**

| Issue | Symptom | Fix |
| --- | --- | --- |
| Margin leakage in negotiation | Agent accepted any ask below the hidden ceiling instantly (a $6,000 ask on a $5,022 load booked at $6,000 — $0 saved) | Rewrote the policy to anchor at the posted rate and counter *below* the ask, conceding toward (never past) the ceiling — savings now captured every call |
| Booking "false failure" | After a successful booking, the agent read the post-booking margin output and told the carrier the load "was taken" | Agent now judges success **only** from `book_load`'s `booking_reference`; analytics output never enters its context |
| Session-ID leak | Agent asked the caller "what's your session ID?" | `session_id` removed as an agent parameter; bound automatically to the run ID server-side |

The security-critical guarantees (OTP never bypassed, ceiling never revealed) held
through all of these — the issues were process/UX and margin-optimization gaps,
caught by live red-teaming and fixed.

**Adversarial tests (manual web calls):** rate-ceiling extraction, book a
non-existent load, and the 3-round negotiation stalemate / forced transfer —
run manually because the automated AI actor cannot obtain the out-of-band OTP
code (which is itself evidence the OTP gate is unbypassable).

---

## 9. Deployment

- **Containerized:** single `Dockerfile` (binds `$PORT`, `/healthz` healthcheck).
- **Cloud:** deployed to Railway, which builds the image on every push to `main`.
- **Single-command:** `railway up`, or git push (auto-deploy); locally
  `docker build && docker run --env-file .env -p 8000:8000`.

**Production activation steps:**
1. **SMS sender** *(Admin-gated on the trial org)* — provision a toll-free/Twilio
   number and select it on the Send SMS node. The OTP request/verify logic is
   unchanged; for the POC the code is read from the run log.
2. **Secret hardening** — move the middleware API key to a platform secret /
   environment variable and rotate it independently of third-party keys.
3. **Operational UI — done.** A native HappyRobot App reads `carrier_calls` live
   via the Twin API gateway; no further action needed beyond the existing access
   controls. (The built-in Analytics dashboard remains as a second surface.)

---

## 10. Live validation

Completed full happy-path calls end-to-end: MC `133655` → FMCSA returns
SCHNEIDER NATIONAL CARRIERS INC (eligible) → OTP issued and verified → real loads
returned from the TMS → negotiated rate → real booking reference issued →
mocked handoff → outcome classified and charted. The agent has been observed
holding the rate line (talking a carrier down from an inflated ask toward the
listed rate) and refusing every adversarial bypass attempt.

---

## 11. Recommended next steps

1. Provision SMS sender and Twin (Admin) to activate texted OTP and persistent
   storage.
2. Harden and rotate the middleware secret.
3. Pilot on a subset of inbound traffic; review the dashboard weekly (booking
   conversion, negotiation savings, verification failures, sentiment).
4. Expand load-search matching (multi-lane, equipment fallbacks) based on pilot
   data.
