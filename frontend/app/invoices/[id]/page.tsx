"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Async, FlagBadge, PageHead, Status, Timeline } from "@/components/ui";
import { getActor, post, useApi } from "@/lib/api";
import { num, usd } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const s = useApi<InvoiceDetail>(`/invoices/${id}`);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject") {
    setBusy(decision); setErr(null);
    try { await post(`/invoices/${id}/decision`, { decision, actor: getActor(), reason }); setReason(""); await s.reload(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }
  async function runMatch() {
    setBusy("match"); setErr(null);
    try { await post(`/invoices/${id}/match`); await s.reload(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }

  return (
    <Async s={s} what="invoice">
      {(i) => {
        const flags = new Set(i.flags ?? []);
        const po = i.purchase_order;
        const qty = (i.line_items ?? []).reduce((a, l) => a + Number(l.qty), 0);
        const price = i.line_items?.[0]?.unit_price;
        const decidable = ["matched", "flagged", "needs_review"].includes(i.status);
        return (
          <>
            <PageHead title={i.invoice_number ?? i.filename ?? `Invoice #${i.id}`} sub={i.vendor_name ?? "Fields could not be extracted"} right={<Status value={i.status} />} />
            {err && <div className="callout" role="alert" style={{ marginBottom: 14 }}>{err}</div>}
            {i.extraction_error && <div className="callout warn" style={{ marginBottom: 14 }}>Extraction failed, so no fields were guessed: {i.extraction_error}</div>}
            {["extracted", "needs_review"].includes(i.status) && <div className="row" style={{ marginBottom: 14 }}><button className="btn" disabled={!!busy} onClick={runMatch}>{busy === "match" ? "Matching…" : "Run three-way match"}</button></div>}

            {i.flag_details.length > 0 && (
              <div className="callout section">
                <div className="row">{i.flag_details.map((f) => <FlagBadge key={f.code} code={f.code} />)}</div>
                {i.exception_summary && <p style={{ margin: "10px 0 0" }}>{i.exception_summary} <em className="muted">({i.exception_summary_source === "llm" ? "AI-written summary" : "rule-generated summary"})</em></p>}
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>{i.flag_details.map((f) => <li key={f.code}><strong>{f.code}</strong>: {f.message}</li>)}</ul>
              </div>
            )}
            {i.status === "matched" && <div className="callout ok section">Three-way match passed: no discrepancies against {po?.po_number}.</div>}

            <div className="grid2 section">
              <section className="card">
                <h2>Extracted from invoice</h2>
                <dl className="kv">
                  <dt>Vendor</dt><dd className={flags.has("VENDOR_MISMATCH") ? "diff" : ""}>{i.vendor_name ?? "-"}</dd>
                  <dt>Invoice no.</dt><dd className={flags.has("DUPLICATE_INVOICE") ? "diff" : ""}>{i.invoice_number ?? "-"}</dd>
                  <dt>Date</dt><dd>{i.invoice_date ?? "-"}</dd>
                  <dt>PO reference</dt><dd className={flags.has("UNKNOWN_PO") ? "diff" : ""}>{i.po_number ?? "none"}</dd>
                  <dt>Quantity</dt><dd className={flags.has("QTY_MISMATCH") ? "diff" : ""}>{i.line_items ? num(qty) : "-"}</dd>
                  <dt>Unit price</dt><dd className={flags.has("PRICE_VARIANCE") ? "diff" : ""}>{price ? usd(price) : "-"}</dd>
                  <dt>Total</dt><dd className={flags.has("TOTAL_MISMATCH") ? "diff" : ""}>{usd(i.total)} {i.currency}</dd>
                  <dt>Confidence</dt><dd className={flags.has("LOW_CONFIDENCE") ? "diff" : ""}>{i.confidence == null ? "-" : `${Math.round(i.confidence * 100)}%`}</dd>
                </dl>
                {i.line_items && i.line_items.length > 1 && <p className="muted">{i.line_items.length} line items; first shown.</p>}
                {i.raw_text && <details style={{ marginTop: 12 }}><summary>Raw document text (treated as untrusted data)</summary><pre>{i.raw_text}</pre></details>}
              </section>
              <section className="card">
                <h2>Matched purchase order</h2>
                {po ? (
                  <dl className="kv">
                    <dt>PO</dt><dd>{po.po_number}</dd><dt>Vendor</dt><dd>{po.vendor_name}</dd>
                    <dt>Item</dt><dd>{po.item}</dd><dt>Quantity</dt><dd>{po.quantity}</dd>
                    <dt>Unit price</dt><dd>{usd(po.unit_price)}</dd><dt>PO total</dt><dd>{usd(po.total)} {po.currency}</dd>
                  </dl>
                ) : <p className="muted">{i.status === "extracted" ? "Not matched yet." : "No purchase order found for this invoice."}</p>}
              </section>
            </div>

            {i.payment && (
              <div className="callout ok section">
                <span className="badge sim">simulated</span> Payment {i.payment.reference} of <strong className="mono">{usd(i.payment.amount)}</strong> recorded. No funds moved; this demo has no bank integration.
              </div>
            )}
            {i.decision_reason && <p className="muted">Decision reason: {i.decision_reason}</p>}

            {decidable && (
              <section className="card section">
                <h2>{i.status === "matched" ? "Approval needed (over the auto-approval limit)" : "Human decision required"}</h2>
                <label className="f">Reason {i.status === "flagged" ? "(required to approve or reject)" : "(required to reject)"}
                  <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder="e.g. Vendor confirmed revised pricing by email" /></label>
                <div className="row" style={{ marginTop: 14 }}>
                  <button className="btn btn-ok" disabled={!!busy || i.status === "needs_review" || (i.status === "flagged" && reason.trim().length < 3)} onClick={() => decide("approve")}>{busy === "approve" ? "Approving…" : "Approve and pay (simulated)"}</button>
                  <button className="btn btn-no" disabled={!!busy || reason.trim().length < 3} onClick={() => decide("reject")}>Reject</button>
                </div>
              </section>
            )}
            <section className="card section"><h2>Audit trail</h2><Timeline items={i.timeline} /></section>
          </>
        );
      }}
    </Async>
  );
}
