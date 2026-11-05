"use client";
import Link from "next/link";
import { ReactNode } from "react";
import { FLAG_HELP, actionLabel, label, when } from "@/lib/format";
import type { Audit } from "@/lib/types";

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="state" role="status"><span className="spinner" aria-hidden /> Loading {what}…</div>;
}
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>Something went wrong.</strong> {message}
      {retry && <button className="btn btn-ghost" onClick={retry}>Try again</button>}
    </div>
  );
}
export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return <div className="state state-empty"><div className="empty-title">{title}</div>{hint && <p>{hint}</p>}{action}</div>;
}
export function Async<T>({ s, what, children }: { s: { data: T | null; error: string | null; loading: boolean; reload: () => void }; what: string; children: (d: T) => ReactNode }) {
  if (s.loading && !s.data) return <Loading what={what} />;
  if (s.error && !s.data) return <ErrorBox message={s.error} retry={s.reload} />;
  if (!s.data) return null;
  return <>{children(s.data)}</>;
}
const STATUS_LABEL: Record<string, string> = {
  po_created: "PO issued", awaiting_approval: "Awaiting approval", needs_review: "Needs review",
};
export function Status({ value }: { value: string }) {
  const text = STATUS_LABEL[value] ?? label(value);
  return <span className={`badge st-${value}`}>{text.charAt(0).toUpperCase() + text.slice(1)}</span>;
}
export function FlagBadge({ code }: { code: string }) {
  return <span className="badge flag" title={FLAG_HELP[code] ?? code}>{code}</span>;
}
export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <header className="page-head">
      <div><h1>{title}</h1>{sub && <p className="sub">{sub}</p>}</div>
      {right}
    </header>
  );
}
export function Timeline({ items, linkEntity }: { items: Audit[]; linkEntity?: boolean }) {
  if (!items.length) return <Empty title="No events yet" />;
  return (
    <ol className="timeline">
      {items.map((a) => (
        <li key={a.id}>
          <div className="tl-head">
            <span className="tl-action">{actionLabel(a.action)}</span>
            <span className="tl-actor">{a.actor}</span>
            <time>{when(a.created_at)}</time>
          </div>
          <div className="tl-detail">{a.detail}</div>
          {linkEntity && (
            <Link className="tl-link" href={a.entity_type === "invoice" ? `/invoices/${a.entity_id}` : a.entity_type === "request" ? `/requests/${a.entity_id}` : "/requests"}>
              {label(a.entity_type)} #{a.entity_id}
            </Link>
          )}
        </li>
      ))}
    </ol>
  );
}
