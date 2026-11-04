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
