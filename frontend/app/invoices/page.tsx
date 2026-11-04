"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DragEvent, useRef, useState } from "react";
import { Async, Empty, FlagBadge, PageHead, Status } from "@/components/ui";
import { api, getActor, post, useApi } from "@/lib/api";
import { usd, when } from "@/lib/format";
import type { InvoiceDetail, InvoiceSummary } from "@/lib/types";

function Uploader() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(file: File) {
    setErr(null);
    const ext = file.name.toLowerCase().split(".").pop();
    if (ext !== "pdf" && ext !== "txt") { setErr("Only PDF or TXT invoices are accepted."); return; }
    if (file.size > 5 * 1024 * 1024) { setErr("File is larger than 5 MB."); return; }
    try {
      setStep("Uploading and extracting fields…");
      const fd = new FormData(); fd.append("file", file); fd.append("actor", getActor());
      const inv = await api<InvoiceDetail>("/invoices/upload", { method: "POST", body: fd });
      setStep("Running three-way match…");
      await post(`/invoices/${inv.id}/match`);
      router.push(`/invoices/${inv.id}`);
    } catch (e) { setErr(e instanceof Error ? e.message : "Upload failed"); setStep(null); }
  }
  function onDrop(e: DragEvent) { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) void run(f); }

  return (
    <div className={`drop ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
      {step ? <div className="state" role="status" style={{ border: 0 }}><span className="spinner" /> {step}</div> : (
        <>
          <h2 style={{ marginBottom: 4 }}>Drop an invoice here</h2>
          <p className="muted">PDF or TXT, up to 5 MB. Fields are extracted by AI, then checked by rules against the PO.</p>
          <button className="btn" onClick={() => input.current?.click()}>Choose a file</button>
          <input ref={input} type="file" accept=".pdf,.txt" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(f); e.target.value = ""; }} />
        </>
      )}
      {err && <div className="err-inline" role="alert">{err}</div>}
    </div>
  );
}

export default function InvoicesPage() {
  const s = useApi<InvoiceSummary[]>("/invoices");
  return (
    <>
      <PageHead title="Invoices" sub="Upload a vendor invoice. It is extracted, three-way matched against the PO, and routed." />
      <Uploader />
      <section className="section">
        <Async s={s} what="invoices">
          {(rows) => rows.length === 0 ? <Empty title="No invoices yet" hint="Upload one above to see the match." /> : (
            <div className="card table-wrap"><table>
              <thead><tr><th>Invoice</th><th>Status</th><th>PO</th><th>Flags</th><th className="n">Total</th><th>Received</th></tr></thead>
              <tbody>{rows.map((i) => (
                <tr key={i.id}>
                  <td><Link href={`/invoices/${i.id}`}><strong>{i.invoice_number ?? i.filename ?? `#${i.id}`}</strong></Link><div className="muted">{i.vendor_name ?? "unreadable"}</div></td>
                  <td><Status value={i.status} /></td><td className="mono">{i.po_number ?? "-"}</td>
                  <td>{(i.flags ?? []).length ? (i.flags ?? []).map((f) => <FlagBadge key={f} code={f} />) : <span className="muted">none</span>}</td>
                  <td className="n">{usd(i.total)}</td><td>{when(i.created_at)}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </Async>
      </section>
    </>
  );
}
