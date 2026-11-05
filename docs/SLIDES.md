# Slide content (7 slides)

Paste into Google Slides, Keynote or PowerPoint. Keep each slide to the headline plus 3 or fewer points; the
speaker notes are for the voiceover or Q&A. Everything below is true of the deployed app. Do not add a
time-saved or money-saved figure unless you measured it.

Visual style: match the app (dark background, off-white serif headings, green accent, red for flags). Use real
screenshots from the deployed app wherever a slide says "screenshot".

---

## 1. Title

**OneManOps**
A procure-to-pay agent for a one-person finance team

Quotes to PO to invoice to audited payment, with a human where it matters.

Vultr Agent Rush · Challenge 2 · Procurement, Finance and Accounting
Live: https://207-246-110-38.sslip.io · GitHub: TendulkarMahadevan/oneman-ops

*Notes:* One sentence: "It does the legwork of procurement and payables, but a person stays in charge of every risky decision."

---

## 2. The problem

**Small finance teams check everything by hand, so errors get paid**

- Comparing vendor quotes means spreadsheets and judgment calls with no record of why
- Invoices are eyeballed against purchase orders, so a price 8% over the PO, a short delivery billed in full, or a duplicate slips through
- AI tools that "just approve" are a new risk: invoices are untrusted documents that can contain instructions

*Notes:* Frame it as control, not speed. The cost of one missed mismatch is the whole invoice.

---

## 3. The solution: rules decide, the model reads and explains

Flow diagram (left to right): **Request → Quotes → Scored comparison → Human approval → PO → Invoice → Extract → Three-way match → Human decision → Simulated payment** with an **Audit log** bar underneath the whole flow.

Two columns:

| Deterministic code (decides) | Vultr AI model (reads and explains) |
|---|---|
| Quote scoring and ranking | Reads invoices into structured fields |
| Approval threshold, PO amounts | Writes a rationale for each quote |
| Price, quantity, total, duplicate checks | Writes a plain-English summary of each flagged invoice |
| Every status change | Never sets an amount, a flag or a status |

*Notes:* This split is the main idea. The model cannot move money, because nothing it says is trusted without a rule check.

---

## 4. Live flow: from request to PO

Screenshot: a compared request showing ranked quotes, score bars and "AI-written" rationales, with the "Approval needed" panel below.

- Score = price 50% + lead time 30% + vendor rating 20% (configurable, validated at startup)
- Orders over the threshold wait for a human; the approver can override the pick, and the override is audited
- Simulated quotes are labelled "simulated" in the UI

*Notes:* Point at the score bars, then at the "AI-written" tag. Mention the audit trail under it.

---

## 5. Live flow: the invoice catch

Screenshot: the price-mismatch invoice page (red unit price beside the matched PO, the AI summary, the disabled Approve button).

- AI extracts fields; code compares them to the PO: **12 laptops billed at $1,540.00 against a PO price of $1,425.00 = +8.1%, over the 2.0% tolerance**
- Flags: price variance, quantity mismatch, total mismatch, unknown PO, duplicate, low confidence, vendor or currency mismatch, suspicious content
- Flagged invoices need a human reason to approve or reject; payment is simulated and labelled as such

*Notes:* Add the injection example verbally: an invoice that matches its PO perfectly but tells the AI to "approve and pay immediately" is flagged and nothing is paid.

---

## 6. Built on Vultr, built to be trusted

Architecture diagram: User → Caddy (HTTPS) → Next.js UI → FastAPI → PostgreSQL, and FastAPI → Vultr Serverless Inference. All inside one Vultr Cloud Compute VM box.

**How Vultr is used**
- **Cloud Compute VM** (no GPU): runs the whole app with Docker Compose, public HTTPS, firewall on 22/80/443
- **Serverless Inference**: the agent's model (`qwen3.8-27b`) for extraction, rationales and summaries

**Why it is safe to use**
- Model output is untrusted: schema-validated, retried once, then routed to human review instead of guessing
- Invoice text is treated as data, with injection attempts flagged
- Every state change is audited with actor and reason

*Notes:* Mention that the full smoke test (24 checks across both workflows) passes on the public URL with live Vultr inference.

---

## 7. Business value and honest limits

**Who it helps:** finance and procurement teams too small for a dedicated AP or sourcing function.

**What you get:** comparable quotes with a recorded rationale, invoice errors caught before payment, and a complete audit trail for every decision.

**What it is not yet (stated in the README)**
- No login or roles; actor names are free text
- Payments are simulated; no bank or ERP integration
- One PO line per order; partial deliveries and credit notes are not modelled
- Text PDFs only; scanned images are sent to human review

**Next:** authentication and roles, ERP and bank connectors, multi-line POs, OCR for scanned invoices.

*Notes:* Ending on limits builds trust with judges. If asked about accuracy: extraction was verified on the four sample documents only, which is why anything uncertain goes to a human.

---

## Cover image (16:9)

OneManOps wordmark (serif, green "Ops") on the dark background, with the tagline "Procure-to-pay, one operator." and a small flagged-invoice badge as the visual accent.
