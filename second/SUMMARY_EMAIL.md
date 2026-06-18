# Summary Email — Inbound Carrier Sales Automation (POC)

**To:** [Carrier Sales lead], HappyRobot Logistics
**From:** Roberto Arce
**Subject:** Inbound Carrier Sales — working proof of concept + next steps

---

Hi [Name],

Following our deployment-strategy session, I've built and deployed a working
proof of concept that automates the first leg of your inbound carrier desk — the
part that's currently eating your dispatchers' time during peak hours.

**What it does.** A carrier calls in (web-based voice, no phone number to
provision) and the AI agent handles the whole opening conversation on its own:

1. Collects the **MC number**, reads it back to confirm, and **verifies operating
   authority against the live FMCSA registry**.
2. Sends a **one-time passcode** and confirms it before going any further — and it
   refuses to skip this under any pressure.
3. Searches your **TMS** for matching loads on the carrier's lane and equipment.
4. **Pitches a load and negotiates the rate** — capped at three rounds, and it
   never reveals or exceeds your internal maximum.
5. **Books the load** and hands off to a senior rep to finalize.
6. **Logs every call** (carrier, load, agreed rate, outcome, sentiment) to a
   database that feeds a live operations dashboard — a purpose-built carrier-desk
   view (booking conversion, negotiation savings, verification failures, recent
   calls) your team can open in the browser.

**What's working today.** The full flow has been validated with live calls end to
end — real FMCSA lookups (e.g., a verified national carrier), real loads from the
TMS, real bookings with confirmation references, all logged and charted. The
integration is containerized and deployed to the cloud, and the legacy-TMS
connection is hardened against the timeouts and malformed responses that system
is known for.

**Why it matters to your numbers.** Three of your stated pain points are directly
addressed:
- **Margin leakage** → rate negotiation is consistent and policy-bound; the
  ceiling is enforced server-side and can't be talked out of the agent. The
  dashboard tracks average negotiation savings per booked load.
- **Missed calls / peak load** → the agent answers instantly, 24/7, in parallel.
- **No audit trail** → every call is now a structured, queryable record.

**Quality & safety.** We ran an adversarial test suite (graded automatically
against defined quality criteria) plus manual red-team calls — attempts to skip
verification, extract the rate ceiling, brute-force the passcode, and force a
transfer after a failed negotiation. The agent held the line on every
security-critical case; two minor process gaps it surfaced have been fixed and
re-verified.

**One production step.** Sending the verification code by SMS needs a phone
sender provisioned on your workspace (an admin action). The passcode logic is
fully built; for the POC the code is confirmed via the call record. Everything
else is live.

**Links**
- Demo video (~5 min): [link]
- Code repository: [link]
- HappyRobot workflow: [link]
- Operations dashboard (HappyRobot App): https://platform.happyrobot.ai/fderobertoarce/apps/carrier-call-app-35v50

**Suggested next steps**
1. Provision the SMS sender (the one remaining infra item).
2. Pilot the agent on a slice of inbound traffic and review the dashboard weekly.
3. Tune load-matching and negotiation thresholds from real pilot data.

Happy to walk through it live whenever works for you.

Best,
Roberto Arce
