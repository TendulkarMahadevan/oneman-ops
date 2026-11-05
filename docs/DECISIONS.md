# Decisions log

Ambiguities in the brief, resolved with the simplest defensible option.

1. **No scaffold existed.** The brief assumed an existing scaffold; none was available, so the project was built from scratch as a standalone repo.
2. **Approval gate runs at `compare`.** The recommended (rank 1) quote's total decides: above `APPROVAL_REQUIRED_OVER_USD` -> `awaiting_approval`; otherwise the request auto-approves and a PO is issued by actor `system` (audited as `auto_approved`). A human approver may override the recommended quote; the override is written to the audit trail.
3. **Quotes are locked after `compare`.** Adding quotes is only allowed in `open`/`quoted`, so a comparison can never be silently invalidated.
4. **Idempotency.** Re-calling `approve` on a request that already has a PO, or `compare` on an already-compared request, returns the stored result and writes no new audit rows. `reject` after approval is a 409.
5. **Simulated quotes** are deterministic (seeded by request+vendor id), stored with `source="simulated"` and shown as such. They are a demo convenience, never presented as real vendor responses.
6. **Rationale provenance.** Each quote stores `rationale_source` (`llm` | `template`). If the LLM is unavailable or returns invalid/mismatched JSON twice, a deterministic template text is used and labelled as such.
7. **PO numbers** are `PO-(1000+id)`, deterministic for the seed.
8. **No authentication.** Actor names are free text supplied by the client. Out of scope for a 4-day demo; stated as a limitation in the README.
9. **Money** is `Decimal`/`Numeric` end to end; serialised as strings.
10. **Extra flags beyond the brief:** `VENDOR_MISMATCH` (invoice vendor differs from the PO vendor), `CURRENCY_MISMATCH`, and `SUSPICIOUS_CONTENT` (regex detector for text that addresses an AI). Each is deterministic and cheap, and the first is a standard AP fraud check. Any flag means `flagged`, as the brief requires.
11. **`TOTAL_MISMATCH` is arithmetic only**: stated total vs the sum of the invoice's own lines (0.02 tolerance). Deviation from the PO is caught by price/quantity flags, so a within-tolerance price difference does not also trip a total flag.
12. **Auto-approval of clean invoices.** A `matched` invoice at or under `APPROVAL_REQUIRED_OVER_USD` is approved and paid (simulated) by `system`, audited as `auto_approved`. Over the threshold it waits for a human. Flagged and low-confidence invoices always wait for a human, per the brief.
13. **Failed extraction never guesses.** LLM invalid after one retry, an unreadable PDF or an unconfigured LLM all give `needs_review`; matching then produces `LOW_CONFIDENCE`, and such an invoice can only be rejected (approval needs extracted fields).
14. **Exception summaries are built from rule output only** (flag codes, rule-written findings, PO facts), never the raw invoice text, so injected text cannot reach that prompt. If the LLM fails, a deterministic template is used and labelled `template`.
15. **One PO line, whole-PO matching.** A PO has a single item/price. Each invoice is matched against the whole PO; partial deliveries across several invoices are a documented limitation, not modelled.
16. **Seeded invoices bypass LLM extraction** (fields are supplied directly, audited as `invoice_seeded`) so the seed works offline. Live uploads always go through extraction. `samples/` holds uploadable demo files that line up with the seeded POs.
17. **UI stack:** plain CSS and system fonts (no UI library, no web-font fetch), so the build has no external dependencies at runtime. The `frontend-design` skill named in the brief was not available in this environment; the look (paper/ink "ledger" palette, serif headings, monospace figures) was designed by hand.
18. **Score weights come from the API** (`score_weights` on request detail), so the UI never hardcodes the 50/30/20 split.
19. **Public routing:** Caddy sends `/health` to the backend and everything else to Next.js, which proxies `/api/*` to the backend. The backend's `/docs` and raw API are not exposed publicly.
20. **Seed is a command, not automatic.** `docker compose exec backend python -m app.seed` loads demo data; the schema itself is created on backend start. No manual SQL is needed anywhere.
21. **Phases 4-5 prepared, not executed:** deploy files, bootstrap script, smoke test and submission kit are written; running them needs a Vultr account, domain and recorded video.
22. **`/health` makes a real authenticated 1-token call** (cached 60 s). The public `/models` listing returns 200 even for a bad key, so it cannot prove credentials work.
23. **Rationale prompts use vendor names, not ids**, after the first live run showed the model quoting internal ids ("Quote 14").
24. **Deployed model:** `qwen3.8-27b` on Vultr Serverless Inference. It returns its reasoning in a separate field, so `content` stays clean JSON; JSON mode was accepted.
