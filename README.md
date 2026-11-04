# OneManOps

**A procurement-to-payment agent for a one-person finance team.** It takes a purchase request through vendor quotes, comparison, human approval and PO creation. It then reads the vendor invoice with an LLM, three-way matches it (request / PO / invoice), flags anomalies and routes exceptions to a human. Every step is audited.

Built for the lablab.ai **Vultr Agent Rush**, Challenge 2 (Powering the Future of Work). Focus areas: Procurement, Finance and Accounting.

> **Rules decide, the LLM explains and extracts.** Scoring, tolerances, thresholds, totals and status changes are deterministic, unit-tested Python. The LLM reads invoices and writes explanations, and its output is validated as untrusted input.

- Public URL: `https://<your-domain>` (fill in after deploy, see [docs/DEPLOY.md](docs/DEPLOY.md))
- Demo video: _link to be added at submission_

## What it does

1. **Request and quotes.** Create a purchase request; add vendor quotes by hand or simulate them (simulated quotes are labelled as such in the UI).
2. **Compare.** A deterministic weighted score (price 50%, lead time 30%, vendor rating 20%, configurable) ranks the quotes. The LLM writes a short rationale for each, with a labelled template fallback.
3. **Approve.** Orders above `APPROVAL_REQUIRED_OVER_USD` wait for a human; smaller ones auto-approve. Approval issues a PO for the chosen vendor, quantity and price. Overriding the recommended vendor is allowed and audited.
4. **Invoice.** Upload a PDF or text invoice. The LLM extracts `{vendor, invoice_number, date, po_number, line_items, total, currency, confidence}`, validated by Pydantic.
5. **Three-way match.** Deterministic flags: `PRICE_VARIANCE`, `QTY_MISMATCH`, `TOTAL_MISMATCH`, `UNKNOWN_PO`, `DUPLICATE_INVOICE`, `LOW_CONFIDENCE`, plus `VENDOR_MISMATCH`, `CURRENCY_MISMATCH` and `SUSPICIOUS_CONTENT` (text that addresses an AI). No flags means `matched`; any flag means `flagged`.
6. **Exceptions.** Flagged invoices get a plain-English summary and suggested action, and wait in the approvals queue. A human approves (reason required) or rejects. Approved invoices move to `paid` as a **simulated** payment record; no money moves.
7. **Audit.** Every state change writes who, what and why. Filterable in the UI.

Clean invoices at or under the threshold are approved and paid (simulated) without a human; everything flagged, low-confidence, or over the threshold needs one.

## How Vultr is used

| Vultr service | Role |
|---|---|
| **Cloud Compute VM** (no GPU) | Orchestration backend: runs Docker Compose with FastAPI, Next.js, PostgreSQL and Caddy (automatic HTTPS). Public URL served from here. |
| **Serverless Inference** (`https://api.vultrinference.com/v1`, OpenAI-compatible) | The agent's brain: structured invoice extraction, per-quote rationales, exception summaries. Called from `backend/app/llm.py`. |
| Firewall group | Inbound 22/80/443 only. |

No Vultr Marketplace apps are used. Architecture and trust boundaries: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
user -> Caddy (TLS) -> Next.js UI -> /api/* -> FastAPI -> PostgreSQL
                                                  \-> Vultr Serverless Inference
```

## Run locally

Requirements: Python 3.12+, Node 20+. SQLite is used unless `DATABASE_URL` points at Postgres.

```bash
cp .env.example .env            # add VULTR_INFERENCE_API_KEY and VULTR_INFERENCE_MODEL
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                 # unit + API tests
python -m app.seed               # 6 vendors, 3 requests with POs, 4 sample invoices (idempotent)
python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Without an inference key the app still runs: rationales and summaries use labelled templates, and uploaded invoices land in `needs_review` (extraction needs the LLM). The seeded invoices bypass extraction so the matching demo works offline.

Demo files for live upload are in `samples/` (regenerate with `scripts/make_sample_invoices.py`): a clean invoice, a price mismatch, a quantity mismatch and a prompt-injection attempt. Upload the clean one twice to see `DUPLICATE_INVOICE`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VULTR_INFERENCE_API_KEY` / `_MODEL` / `_BASE_URL` | empty / empty / Vultr URL | Inference credentials. Model is required when a key is set. |
| `DATABASE_URL` | SQLite file | Compose builds a Postgres URL from `POSTGRES_*`. |
| `APPROVAL_REQUIRED_OVER_USD` | 5000 | Human approval threshold (orders and clean invoices). |
| `INVOICE_PRICE_TOLERANCE_PCT` | 2.0 | Allowed unit-price deviation from the PO. |
| `LOW_CONFIDENCE_THRESHOLD` | 0.7 | Extraction confidence below this is flagged. |
| `SCORE_WEIGHT_PRICE` / `_LEAD_TIME` / `_RATING` | 0.5 / 0.3 / 0.2 | Must sum to 1.0 (validated at startup). |
| `UPLOAD_DIR`, `MAX_UPLOAD_MB` | `uploads`, 5 | Upload location and size limit (PDF/TXT only). |
| `SITE_ADDRESS` | `localhost` | Public hostname for Caddy. |

Secrets live only in `.env` (gitignored). Configuration is validated on startup.

## Deploy

See [docs/DEPLOY.md](docs/DEPLOY.md): Vultr VM, firewall, DNS, `deploy/bootstrap_vm.sh`, `docker compose up -d --build`, seed, then `python scripts/smoke_test.py https://<your-domain>`.

## Verification status

Be skeptical of anything not on this list.

| Check | Status |
|---|---|
| `pytest`: scoring, matching (every flag and boundary), state machine, LLM validation/retry, procurement and invoice APIs, seed | 75 tests passing |
| Seeded invoices give clean=paid, price/qty/duplicate=flagged with the expected single flag | Verified (tests + local run) |
| Full smoke test (`scripts/smoke_test.py`) through the Next.js `/api` proxy against local PostgreSQL 16 | Passed, **using a local OpenAI-compatible stub in place of Vultr inference** |
| UI journey in a real browser (create, simulate, compare, approve, upload, decide, audit filter), mobile width has no horizontal overflow | Verified locally |
| Calls to **live Vultr Serverless Inference** (real extraction quality, model JSON compliance) | **Not yet tested** |
| `docker compose build/up` and the **Vultr VM deployment**, HTTPS on a real domain | **Not yet done**; compose file validates, Docker images not built in the authoring environment |

## Limitations

- **No authentication or roles.** Actor names are free text recorded in the audit log. Do not expose a production instance without adding auth.
- **Payments are simulated.** There is no bank or ERP integration.
- **Simulated quotes** are deterministic demo data, labelled as such. There is no real vendor RFQ channel.
- **One PO line item.** A PO has a single item and price, and each invoice is matched against the whole PO. Partial deliveries across several invoices, freight lines and credit notes are not modelled.
- **Text PDFs only.** Scanned image PDFs are rejected to human review; there is no OCR.
- **LLM extraction can be wrong.** The rules catch inconsistencies (arithmetic, PO mismatch, duplicates, low confidence), but a confidently wrong extraction that is internally consistent with the PO would pass. Human review of the original document remains the control for high-value invoices, which is why anything over the threshold needs approval.
- Prompt-injection defences reduce risk but are not a guarantee; the real safeguard is that the LLM cannot trigger actions or set amounts without rule checks.
- Vendor-name matching is normalised-exact (case, punctuation, common suffixes), not fuzzy.

## Repo layout

```
backend/    FastAPI app (app/), tests (tests/), Dockerfile
frontend/   Next.js 14 app router UI, Dockerfile
deploy/     Caddyfile, VM bootstrap script
docs/       ARCHITECTURE.md, DEPLOY.md, DECISIONS.md, SUBMISSION.md
samples/    Demo invoices for live upload
scripts/    smoke_test.py, make_sample_invoices.py, capture_screenshots.js
```

Design decisions and resolved ambiguities: [docs/DECISIONS.md](docs/DECISIONS.md).
