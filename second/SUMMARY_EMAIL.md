# Summary Email — Inbound Carrier Sales Automation (POC)

**To:** [Name], Carrier Sales lead, HappyRobot Logistics
**From:** Roberto Arce
**Subject:** Inbound Carrier Sales — working proof of concept + next steps

---

Hi [Name],

Following our session, I've built and deployed a working proof of concept that
automates the first leg of your inbound carrier desk — the part that's currently
eating your dispatchers' time during peak hours.

**What are the benefits?**

- **Margin leakage on negotiated rates.** Today, what a carrier gets talked into
  varies by whoever picks up the phone. The agent negotiates the same disciplined
  way on every call — and it never even *sees* your maximum rate, so it physically
  can't be talked into leaking it or going above it. The dashboard shows your
  average savings per booked load.
- **Missed calls when volume spikes.** Calls that go to voicemail at peak are
  loads you don't cover. The agent answers instantly, around the clock, and
  handles many calls at the same time — so nothing sits in a queue.
- **No audit trail.** Right now there's no clean record of who called, what was
  offered, or why a load did or didn't book. Every call is now a structured,
  searchable record feeding a dashboard your team opens in the browser.
  
**How it works.** 

A carrier calls in (over the web — no phone line to set up) and
the AI agent runs the whole opening conversation on its own:

1. Takes the **MC number**, reads it back to confirm, and checks **authority
   against the live FMCSA registry**.
2. Sends a **one-time passcode** and confirms it before doing anything else — and
   won't skip it no matter how the caller pushes.
3. Searches your **TMS** for loads on the carrier's lane and equipment.
4. Pitches a load and **negotiates the rate** — up to three rounds, and it never
   reveals or goes above your internal maximum.
5. **Books the load** and hands off to a senior rep to finalize.
6. **Logs every call** — carrier, load, agreed rate, outcome, sentiment — into a
   live operations dashboard your team opens in the browser (booking conversion,
   negotiation savings, verification failures, recent calls).

**Quality & safety.** I stress-tested it the way a bad actor would — trying to
skip verification, fish out your rate ceiling, brute-force the passcode, and force
a transfer after a failed negotiation. It held the line on every one. Two smaller
process gaps it surfaced are fixed and re-checked.

**Links**

Here is the Operations dashboard:

(HappyRobot App): https://platform.happyrobot.ai/fderobertoarce/apps/carrier-call-app-35v50


Happy to walk through it live whenever works for you.

Best Regards,
Roberto Arce
