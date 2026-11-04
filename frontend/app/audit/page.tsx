"use client";
import { useState } from "react";
import { Async, Empty, PageHead, Timeline } from "@/components/ui";
import { useApi } from "@/lib/api";
import { label } from "@/lib/format";
import type { Audit } from "@/lib/types";

type Facets = { actors: string[]; actions: string[]; entity_types: string[] };

export default function AuditPage() {
  const [f, setF] = useState({ entity_type: "", actor: "", action: "", q: "" });
  const facets = useApi<Facets>("/audit/facets");
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const s = useApi<Audit[]>(`/audit?limit=200${qs ? `&${qs}` : ""}`);
  const sel = (k: keyof typeof f, name: string, opts: string[] = []) => (
    <label className="f">{name}
      <select value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}>
        <option value="">All</option>{opts.map((o) => <option key={o} value={o}>{label(o)}</option>)}
      </select></label>
  );
  return (
    <>
      <PageHead title="Audit log" sub="Every state change, who made it, and why. Newest first." />
      <div className="filters">
        {sel("entity_type", "Entity", facets.data?.entity_types)}
        {sel("actor", "Actor", facets.data?.actors)}
        {sel("action", "Action", facets.data?.actions)}
        <label className="f">Search detail<input value={f.q} maxLength={100} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="e.g. PRICE_VARIANCE" /></label>
      </div>
      <Async s={s} what="audit log">
        {(rows) => rows.length === 0 ? <Empty title="No matching events" hint="Clear a filter to see more." /> : <div className="card"><Timeline items={rows} linkEntity /></div>}
      </Async>
    </>
  );
}
