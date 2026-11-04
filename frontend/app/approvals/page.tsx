"use client";
import Link from "next/link";
import { Async, Empty, FlagBadge, PageHead } from "@/components/ui";
import { useApi } from "@/lib/api";
import { usd, when } from "@/lib/format";
import type { ApprovalItem } from "@/lib/types";

export default function ApprovalsPage() {
  const s = useApi<ApprovalItem[]>("/approvals");
  return (
    <>
      <PageHead title="Approvals queue" sub="Everything waiting on a human: orders over the threshold and invoices the rules could not clear." />
      <Async s={s} what="approvals">
        {(rows) => rows.length === 0 ? <Empty title="Nothing is waiting on you" hint="New orders over the threshold and flagged invoices will appear here." /> : (
          <div className="card table-wrap"><table>
            <thead><tr><th>Item</th><th>Why it is here</th><th className="n">Amount</th><th>Since</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={`${r.kind}-${r.id}`}>
                <td><span className="badge">{r.kind}</span> <strong>{r.title}</strong></td>
                <td>{r.reason}<div>{r.flags.map((f) => <FlagBadge key={f} code={f} />)}</div></td>
                <td className="n">{usd(r.amount_usd)}</td><td>{when(r.created_at)}</td>
                <td><Link className="btn" style={{ textDecoration: "none", display: "inline-block" }} href={r.kind === "request" ? `/requests/${r.id}` : `/invoices/${r.id}`}>Review</Link></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Async>
    </>
  );
}
