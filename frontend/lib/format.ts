export const usd = (v: string | number | null | undefined) =>
  v == null ? "-" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(v));
export const num = (v: string | number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(Number(v));
export const when = (iso: string) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
export const label = (s: string) => s.replace(/_/g, " ");
export const FLAG_HELP: Record<string, string> = {
  PRICE_VARIANCE: "Unit price outside tolerance", QTY_MISMATCH: "Quantity differs from PO", TOTAL_MISMATCH: "Total does not add up",
  UNKNOWN_PO: "No matching PO", DUPLICATE_INVOICE: "Already received", LOW_CONFIDENCE: "Extraction uncertain",
  VENDOR_MISMATCH: "Vendor differs from PO", CURRENCY_MISMATCH: "Currency differs from PO", SUSPICIOUS_CONTENT: "Text addresses an AI",
};
export const actionLabel = (s: string) => {
  const t = label(s).replace(/\bpo\b/g, "PO");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
