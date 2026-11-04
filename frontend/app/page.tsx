"use client";
import Link from "next/link";
import { Async, PageHead, Timeline } from "@/components/ui";
import { useApi } from "@/lib/api";
import { usd } from "@/lib/format";
import type { Dashboard, Health } from "@/lib/types";

const cycle = (h: number | null) => h == null ? "-" : h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;

function Kpi({ l, v, s, href, hot }: { l: string; v: string | number; s?: string; href: string; hot?: boolean }) {
  return (
    <Link href={href} className={`kpi ${hot ? "hot" : ""}`}>
      <div className="kpi-l">{l}</div><div className="kpi-v">{v}</div>{s && <div className="kpi-s">{s}</div>}
    </Link>
  );
}

export default function DashboardPage() {
  const s = useApi<Dashboard>("/dashboard/summary");
  const h = useApi<Health>("/health");
  return (
    <>
      <PageHead title="Dashboard" sub="Where procurement and payables stand right now."
        right={h.data && (
          <span className="badge" title={`database: ${h.data.database}, inference: ${h.data.llm}`}>
            {h.data.status === "ok" ? "All systems up" : `Degraded: inference ${h.data.llm}`}
          </span>)} />
      <Async s={s} what="dashboard">
        {(d) => (
          <>
            <div className="kpis">
              <Kpi l="Open requests" v={d.open_requests} href="/requests" s="not yet ordered or closed" />
              <Kpi l="Awaiting approval" v={d.awaiting_approval} href="/approvals" hot={d.awaiting_approval > 0} s="requests over threshold" />
              <Kpi l="Flagged invoices" v={d.flagged_invoices} href="/approvals" hot={d.flagged_invoices > 0} s="need a human decision" />
              <Kpi l="PO spend this month" v={usd(d.spend_this_month_usd)} href="/requests" s="committed via purchase orders" />
              <Kpi l="Avg cycle time" v={cycle(d.avg_cycle_time_hours)} href="/requests" s="request to PO" />
              <Kpi l="Touchless invoices" v={`${d.touchless_invoices}/${d.invoices_total}`} href="/invoices" s="matched and paid with no human" />
            </div>
            <section className="section card">
              <h2>Recent activity</h2>
              <Timeline items={d.recent_activity} linkEntity />
              <Link href="/audit">Open the full audit log →</Link>
            </section>
          </>
        )}
      </Async>
    </>
  );
}
