"use client";
import { useParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { Async, PageHead, Status, Timeline } from "@/components/ui";
import { getActor, post, useApi } from "@/lib/api";
import { usd } from "@/lib/format";
import type { Quote, RequestDetail, Vendor } from "@/lib/types";

const STEPS = ["Request", "Quotes", "Compared", "Approval", "PO issued"];
function stepIndex(s: string) {
  return ({ open: 0, quoted: 1, compared: 2, awaiting_approval: 3, approved: 3, po_created: 5, rejected: -1 } as Record<string, number>)[s] ?? 0;
}

function ScoreBar({ q, w }: { q: Quote; w: { price: number; lead_time: number; rating: number } }) {
  const b = q.score_breakdown; if (!b) return <span className="muted">not scored</span>;
  return (
    <div title={`price ${b.price} · lead time ${b.lead_time} · rating ${b.rating}`}>
      <div className="mono"><strong>{(q.score ?? 0).toFixed(2)}</strong></div>
      <div className="bar" aria-label={`score ${q.score}`}>
        <i className="b-price" style={{ width: `${b.price * w.price * 100}%` }} />
        <i className="b-lead" style={{ width: `${b.lead_time * w.lead_time * 100}%` }} />
        <i className="b-rate" style={{ width: `${b.rating * w.rating * 100}%` }} />
      </div>
    </div>
  );
}

export default function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const s = useApi<RequestDetail>(`/procurement/requests/${id}`);
  const vendors = useApi<Vendor[]>("/vendors");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pick, setPick] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");

  async function act(name: string, path: string, body?: unknown) {
    setBusy(name); setErr(null);
    try { await post(`/procurement/requests/${id}${path}`, body); await s.reload(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }
  async function addManual(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await act("manual", "/quotes", { quotes: [{ vendor_id: Number(f.get("vendor")), unit_price: String(f.get("price")), lead_time_days: Number(f.get("lead")) }] });
    e.currentTarget.reset();
  }

  return (
    <Async s={s} what="request">
      {(r) => {
        const idx = stepIndex(r.status);
        const quoted = new Set(r.quotes.map((q) => q.vendor_id));
        const canQuote = r.status === "open" || r.status === "quoted";
        const chosen = r.quotes.find((q) => q.id === (pick ?? r.recommended_quote_id));
        return (
          <>
            <PageHead title={r.title} sub={`${r.quantity} × ${r.item} · requested by ${r.requester}`} right={<Status value={r.status} />} />
            {r.status === "rejected" ? (
              <div className="callout">Rejected: {r.rejection_reason}</div>
            ) : (
              <ol className="steps">{STEPS.map((l, i) => <li key={l} className={i < idx ? "done" : i === idx ? "now" : ""}>{l}</li>)}</ol>
            )}
            {r.justification && <p className="muted">{r.justification}</p>}
            {err && <div className="callout" role="alert" style={{ marginBottom: 14 }}>{err}</div>}

            {r.purchase_order && (
              <div className="callout ok section">
                <h3>Purchase order {r.purchase_order.po_number} issued</h3>
                <p style={{ margin: "4px 0 0" }}>{r.purchase_order.quantity} × {r.purchase_order.item} from <strong>{r.purchase_order.vendor_name}</strong> at {usd(r.purchase_order.unit_price)} = <strong className="mono">{usd(r.purchase_order.total)}</strong></p>
              </div>
            )}

            <section className="card section">
              <div className="row"><h2 style={{ margin: 0 }}>Vendor quotes</h2>
                <div className="legend right"><span className="l-price">price {Math.round(r.score_weights.price * 100)}%</span><span className="l-lead">lead time {Math.round(r.score_weights.lead_time * 100)}%</span><span className="l-rate">rating {Math.round(r.score_weights.rating * 100)}%</span></div></div>
              {r.quotes.length === 0 ? (
                <div className="state state-empty" style={{ marginTop: 12 }}><div className="empty-title">No quotes yet</div><p>Add vendor quotes manually, or simulate vendor responses for a demo.</p></div>
              ) : (
                <div className="table-wrap"><table>
                  <thead><tr><th>#</th><th>Vendor</th><th className="n">Unit price</th><th className="n">Lead</th><th className="n">Total</th><th>Score</th>{r.status === "awaiting_approval" && <th>Choose</th>}</tr></thead>
                  <tbody>
                    {r.quotes.map((q) => (
                      <tr key={q.id} className={q.id === r.recommended_quote_id ? "best" : ""}>
                        <td className="mono">{q.rank ?? "-"}</td>
                        <td><strong>{q.vendor_name}</strong> {q.source === "simulated" && <span className="badge sim" title="Simulated demo quote, not a real vendor response">simulated</span>}
                          <div className="muted">rating {q.vendor_rating}/5 {q.id === r.recommended_quote_id && "· recommended"}</div>
                          {q.rationale && <div className="rationale">{q.rationale} <em>({q.rationale_source === "llm" ? "AI-written" : "rule template"})</em></div>}</td>
                        <td className="n">{usd(q.unit_price)}</td><td className="n">{q.lead_time_days}d</td><td className="n">{usd(q.total)}</td>
                        <td><ScoreBar q={q} w={r.score_weights} /></td>
                        {r.status === "awaiting_approval" && <td><input type="radio" name="pick" aria-label={`Choose ${q.vendor_name}`} style={{ width: "auto" }} checked={chosen?.id === q.id} onChange={() => setPick(q.id)} /></td>}
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              )}

              {canQuote && (
                <div className="section">
                  <div className="row">
                    <button className="btn btn-ghost" disabled={!!busy || r.status !== "open"} onClick={() => act("sim", "/quotes", { simulate: true })}>{busy === "sim" ? "Simulating…" : "Simulate vendor quotes"}</button>
                    <button className="btn" disabled={!!busy || r.quotes.length < 2} onClick={() => act("compare", "/compare")}>{busy === "compare" ? "Comparing…" : "Compare quotes"}</button>
                    {r.quotes.length < 2 && <span className="muted">Needs at least two quotes.</span>}
                  </div>
                  <form onSubmit={addManual} className="form-grid" style={{ marginTop: 14, alignItems: "end" }}>
                    <label className="f">Vendor<select name="vendor" required>{(vendors.data ?? []).filter((v) => !quoted.has(v.id)).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
                    <label className="f">Unit price (USD)<input name="price" type="number" step="0.01" min="0.01" required /></label>
                    <label className="f">Lead time (days)<input name="lead" type="number" min={0} max={730} required /></label>
                    <button className="btn btn-ghost" disabled={!!busy}>Add manual quote</button>
                  </form>
                </div>
              )}
            </section>

            {r.status === "awaiting_approval" && chosen && (
              <section className="card section">
                <h2>Approval needed</h2>
                <p>Order total <strong className="mono">{usd(chosen.total)}</strong> exceeds the {usd(r.approval_threshold_usd)} threshold. Approving issues a PO to <strong>{chosen.vendor_name}</strong>{chosen.id !== r.recommended_quote_id && " (not the recommended vendor, this override will be audited)"}.</p>
                <div className="form-grid">
                  <label className="f">Approval note (optional)<input value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} /></label>
                  <label className="f">Rejection reason<input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder="Required to reject" /></label>
                </div>
                <div className="row" style={{ marginTop: 14 }}>
                  <button className="btn btn-ok" disabled={!!busy} onClick={() => act("approve", "/approve", { approver: getActor(), quote_id: chosen.id, note })}>{busy === "approve" ? "Approving…" : `Approve and issue PO`}</button>
                  <button className="btn btn-no" disabled={!!busy || reason.trim().length < 3} onClick={() => act("reject", "/reject", { actor: getActor(), reason })}>Reject request</button>
                </div>
              </section>
            )}
            <section className="card section"><h2>Audit trail</h2><Timeline items={r.timeline} /></section>
          </>
        );
      }}
    </Async>
  );
}
