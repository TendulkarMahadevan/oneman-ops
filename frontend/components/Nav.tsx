"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getActor, setActor, useApi } from "@/lib/api";
import type { ApprovalItem } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Dashboard" }, { href: "/requests", label: "Requests" }, { href: "/invoices", label: "Invoices" },
  { href: "/approvals", label: "Approvals" }, { href: "/audit", label: "Audit log" },
];

export default function Nav() {
  const path = usePathname();
  const [actor, setA] = useState("demo.approver");
  const queue = useApi<ApprovalItem[]>("/approvals");
  useEffect(() => setA(getActor()), []);
  return (
    <aside className="side">
      <Link href="/" className="brand"><span className="brand-mark">¶</span><span>OneMan<b>Ops</b></span></Link>
      <p className="tag">Procure-to-pay, one operator.</p>
      <nav>
        {LINKS.map((l) => {
          const on = l.href === "/" ? path === "/" : path.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={on ? "on" : ""}>
              {l.label}
              {l.href === "/approvals" && queue.data && queue.data.length > 0 && <span className="count">{queue.data.length}</span>}
            </Link>
          );
        })}
      </nav>
      <label className="actor">
        Acting as
        <input value={actor} maxLength={80} onChange={(e) => { setA(e.target.value); setActor(e.target.value.trim() || "demo.approver"); }} />
        <small>Recorded in the audit log. No login in this demo.</small>
      </label>
    </aside>
  );
}
