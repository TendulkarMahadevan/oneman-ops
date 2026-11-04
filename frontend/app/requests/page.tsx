"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Async, Empty, PageHead, Status } from "@/components/ui";
import { getActor, post, useApi } from "@/lib/api";
import { usd, when } from "@/lib/format";
import type { RequestDetail, RequestSummary } from "@/lib/types";

const CATEGORIES = [["it_hardware", "IT hardware"], ["furniture", "Furniture"], ["software", "Software"], ["general", "General supplies"]];

function NewRequest({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setErr(null);
    try {
      const r = await post<RequestDetail>("/procurement/requests", {
        title: f.get("title"), item: f.get("item"), category: f.get("category"), quantity: Number(f.get("quantity")),
        estimated_unit_price: String(f.get("price")), justification: f.get("why"), requester: getActor(),
      });
      router.push(`/requests/${r.id}`);
    } catch (x) { setErr(x instanceof Error ? x.message : "Failed"); setBusy(false); }
  }
  return (
    <form className="card" onSubmit={submit}>
      <h2>New purchase request</h2>
      <div className="form-grid">
        <label className="f wide">Title<input name="title" required minLength={3} maxLength={160} placeholder="e.g. Standing desks for the design team" /></label>
        <label className="f">Item<input name="item" required minLength={2} maxLength={160} placeholder="Standing desk, 160cm" /></label>
        <label className="f">Category<select name="category">{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="f">Quantity<input name="quantity" type="number" min={1} max={100000} required defaultValue={10} /></label>
        <label className="f">Estimated unit price (USD)<input name="price" type="number" min="0.01" step="0.01" required defaultValue="500" /></label>
        <label className="f wide">Justification<textarea name="why" rows={2} maxLength={2000} /></label>
      </div>
      {err && <div className="err-inline" role="alert">{err}</div>}
      <div className="row" style={{ marginTop: 14 }}>
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create request"}</button>
        <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
}

export default function RequestsPage() {
  const s = useApi<RequestSummary[]>("/procurement/requests");
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHead title="Purchase requests" sub="Each request moves through quotes, comparison, approval and a purchase order."
        right={!open && <button className="btn" onClick={() => setOpen(true)}>New request</button>} />
      {open && <NewRequest onClose={() => setOpen(false)} />}
      <section className={open ? "section" : ""}>
        <Async s={s} what="requests">
          {(rows) => rows.length === 0 ? (
            <Empty title="No purchase requests yet" hint="Create one to start the quote, compare and approve flow." />
          ) : (
            <div className="card table-wrap">
              <table>
                <thead><tr><th>Request</th><th>Status</th><th className="n">Qty</th><th className="n">Est. total</th><th>Requester</th><th>Created</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td><Link href={`/requests/${r.id}`}><strong>{r.title}</strong></Link><div className="muted">{r.item}</div></td>
                      <td><Status value={r.status} /></td>
                      <td className="n">{r.quantity}</td>
                      <td className="n">{usd(Number(r.estimated_unit_price) * r.quantity)}</td>
                      <td>{r.requester}</td><td>{when(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </section>
    </>
  );
}
