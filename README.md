# Inbound Carrier Sales Automation — HappyRobot FDE Challenge

An AI voice agent that automates the first leg of a freight brokerage's inbound
carrier desk: it verifies the carrier, confirms their identity, finds a matching
load, negotiates the rate, books it, and hands off to a senior rep — logging every
call for analytics. Built on the HappyRobot platform + a custom integration
service.

> **Status:** Live and validated end-to-end with real calls (real FMCSA lookups,
> real TMS bookings, every call logged to a Twin database).

## Deliverables

| Deliverable | Link |
| --- | --- |
| Summary email (prospect) | [`second/SUMMARY_EMAIL.md`](second/SUMMARY_EMAIL.md) |
| Build description (IT + business) | [`second/Technical_Summary.md`](second/Technical_Summary.md) |
| Code repository | _this repo_ |
| HappyRobot workflow | _[workflow link]_ |
| Walkthrough video (~5 min) | _[video link]_ |
| Operational UI (HappyRobot App) | https://platform.happyrobot.ai/fderobertoarce/apps/carrier-call-app-35v50 |
| Live middleware | https://happyrobottest-production.up.railway.app |

## Architecture

```mermaid
flowchart LR
    C[Carrier - web call] <--> P[HappyRobot platform<br/>voice agent · workflow · OTP · analytics · Twin]
    P -- HTTPS webhooks, X-API-Key --> M[Carrier Sales Middleware<br/>Python/FastAPI · Docker · Railway]
    M --> F[FMCSA QCMobile API]
    M --> T[(Legacy TMS<br/>raw TCP, fixed-width)]
```

The **middleware** is the integration layer: it translates the platform's clean
REST/JSON calls into the legacy TMS's raw fixed-width TCP protocol (handling its
injected timeouts and malformed responses) and into FMCSA REST lookups. The
platform cannot speak that protocol directly — hence the adapter.

## Call flow

```
verify MC (FMCSA) → OTP → search loads → pitch → negotiate (≤3 rounds, ceiling
hidden) → book → mocked senior-rep handoff → log to Twin
```

## Repository layout

```
second/
  inbound-carrier-sales/   Python middleware (FastAPI)
    app/                   TCP adapter, FMCSA, OTP, negotiation, REST API
    tests/                 17 tests incl. fault-injection fake TMS
    scripts/               TMS/FMCSA exploration probes
    Dockerfile, railway.toml
  platform/                TypeScript SDK scaffold (Northstars, adversarial, workflows)
  Technical_Summary.md     Full build doc (architecture, security, QA, KPIs)
  SUMMARY_EMAIL.md         Prospect summary email
```

## Run & deploy the middleware

Three ways to run it. All read config from environment variables
(`TMS_*`, `FMCSA_WEB_KEY`, `API_KEY`) — see
[`.env.example`](second/inbound-carrier-sales/.env.example).

### Option 1 — Local, direct (development)

```bash
cd second/inbound-carrier-sales
cp .env.example .env          # fill TMS_*, FMCSA_WEB_KEY, API_KEY
pip install -r requirements.txt
python -m pytest              # 29 tests, incl. all documented TMS fault modes
uvicorn app.main:app --reload
```

Runs at `http://localhost:8000`.

### Option 2 — Local, Docker (the same image the cloud runs)

```bash
cd second/inbound-carrier-sales
docker build -t carrier-sales .
docker run --env-file .env -p 8000:8000 carrier-sales
```

Builds the container and runs it at `http://localhost:8000`.

### Option 3 — Cloud, single command (Railway)

The service is containerized and deploys to any cloud that builds a `Dockerfile`.
[`railway.toml`](second/inbound-carrier-sales/railway.toml) pins the Dockerfile
builder + the `/healthz` healthcheck:

```bash
cd second/inbound-carrier-sales
railway up                    # single command: builds image, ships, health-checks
```

Railway also **auto-deploys on every push to `main`**, so a normal `git push`
ships a new build. Set the env vars in the Railway service settings. Live
instance: https://happyrobottest-production.up.railway.app

## Design highlights

- **Fault-tolerant TMS adapter** — one connection per request, reads to the `END`
  terminator, retries transport faults with backoff, never retries semantic
  errors (no double-booking).
- **Rate ceiling never leaves the server** — the LLM only sees accept/counter/reject,
  so it cannot disclose the maximum under any pressure.
- **OTP isolated from the agent** — code generated server-side, never in the
  agent's context; resists social-engineering bypass.
- **One MC verification per call** — prevents credential "fishing."

## QA

- **17 unit tests** against a fake TMS reproducing every documented fault mode.
- **Adversarial suite** (auto-graded against 9 Northstar criteria) + manual
  red-team calls. Two real weaknesses surfaced and were fixed and re-verified
  (accepting a second MC after a fail; getting stuck without advancing the flow);
  the security-critical behaviors held throughout. See
  [`second/Technical_Summary.md`](second/Technical_Summary.md) §8.

## Production notes

- **SMS OTP delivery** needs a provisioned sender (Admin-gated on the trial org);
  the OTP logic is complete and the code is read from the run log for the POC.
- Lead with **Negotiation Savings** (carrier's opening ask − agreed) as the value
  metric; `computed_margin` (listed − agreed) is negative when a deal closes above
  the listed rate but under the hidden ceiling — expected behavior.
