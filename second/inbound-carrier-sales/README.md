# Inbound Carrier Sales — Middleware

REST facade between the HappyRobot voice workflow and:

- the **Legacy TMS** (raw TCP, fixed-width line protocol, fault-injecting),
- the **FMCSA** carrier verification API,
- the **OTP** identity-confirmation flow,
- the server-side **negotiation policy** (MAX_BUY never leaves this service).

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in values
uvicorn app.main:app --reload
```

## Tests

```bash
python -m pytest
```

The suite spins up a local fake TMS that reproduces all documented fault
modes (timeout, partial response, malformed frame, delayed close) and
verifies the adapter retries transport faults but never retries semantic
errors (AUTH_FAILED, UNKNOWN_LOAD, ALREADY_BOOKED, INVALID_RATE...).

## Docker

```bash
docker build -t carrier-sales .
docker run --env-file .env -p 8000:8000 carrier-sales
```

## Endpoints (all require `X-API-Key`)

| Method | Path                  | Purpose                                   |
| ------ | --------------------- | ----------------------------------------- |
| GET    | /healthz              | Liveness (unauthenticated)                |
| GET    | /tms/ping             | DEBUG_ECHO connectivity check             |
| POST   | /carriers/verify      | FMCSA authority check by MC number        |
| POST   | /otp/request          | Issue OTP (code goes to SMS node only)    |
| POST   | /otp/verify           | Verify OTP (3 attempts, 5 min TTL)        |
| POST   | /loads/search         | LOAD_QUERY → JSON                         |
| GET    | /loads/{id}           | LOAD_GET → JSON (MAX_BUY stripped)        |
| POST   | /loads/{id}/book      | LOAD_BOOK                                 |
| POST   | /negotiate/evaluate   | accept / counter / reject (3-round cap)   |

## Call flow

```mermaid
flowchart TD
    A([Carrier starts web call]) --> B[Agent greets, asks for MC number]
    B --> C{"/carriers/verify<br/>(FMCSA authority check)"}
    C -- "not eligible" --> Z1[Politely decline & end call]
    C -- "eligible" --> D["/otp/request — code goes<br/>to SMS node only"]
    D --> E[Platform sends SMS<br/>to registered phone]
    E --> F{"/otp/verify<br/>(carrier reads code back)"}
    F -- "wrong 3x / expired" --> Z2[End call — identity not confirmed]
    F -- "verified" --> G[Collect lane + equipment preference]
    G --> H{"/loads/search<br/>(TCP LOAD_QUERY)"}
    H -- "no matches" --> Z3[Offer to check other lanes / end]
    H -- "matches" --> I[Pitch load: route, dates,<br/>commodity, listed rate]
    I --> J{Carrier response}
    J -- "accepts" --> M
    J -- "not interested" --> Z3
    J -- "counters $X" --> K{"/negotiate/evaluate<br/>round N of 3 (MAX_BUY stays server-side)"}
    K -- "accept" --> M["/loads/{id}/book<br/>(TCP LOAD_BOOK)"]
    K -- "counter" --> I2[Agent states counter-offer] --> J
    K -- "reject (round 3)" --> Z4[Close professionally —<br/>failed negotiation, no transfer]
    M --> N[Mocked transfer to senior rep]
    N --> O[Post-call: AI extraction &<br/>classification → Twin]
    Z1 --> O
    Z2 --> O
    Z3 --> O
    Z4 --> O
    O --> P[Apps dashboard for ops manager]
```

## Architecture

```mermaid
flowchart LR
    subgraph caller [Carrier]
        WC[Browser web call]
    end
    subgraph hr [HappyRobot Platform — no code]
        VA[Voice agent + workflow]
        SMS[SMS node]
        TW[(Twin data layer)]
        APP[Apps dashboard]
    end
    subgraph mw [This service — FastAPI in Docker]
        API[REST endpoints<br/>X-API-Key auth]
        NEG[Negotiation policy<br/>holds MAX_BUY]
        OTP[OTP store]
        TCP[TCP adapter<br/>retry + fault handling]
    end
    EXT1[FMCSA REST API]
    EXT2[(Legacy TMS<br/>raw TCP)]

    WC <--> VA
    VA -- "HTTPS webhooks (JSON)" --> API
    VA --> SMS
    VA --> TW --> APP
    API --> NEG
    API --> OTP
    API --> TCP -- "pipe-delimited lines" --> EXT2
    API --> EXT1
```

## Security design

- The voice agent never receives `MAX_BUY`: negotiation decisions are made
  server-side, so the LLM cannot be social-engineered into revealing the
  ceiling.
- The OTP code is returned only to the workflow's SMS-send node and is never
  placed in the agent's conversational context.
- One TCP connection per TMS request per spec; retries with exponential
  backoff on transport faults only.
