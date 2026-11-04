export type Audit = { id: number; entity_type: string; entity_id: number; actor: string; action: string; detail: string; created_at: string };
export type Vendor = { id: number; name: string; category: string; rating: number; email: string };
export type Quote = {
  id: number; vendor_id: number; vendor_name: string; vendor_rating: number; unit_price: string; lead_time_days: number;
  total: string; source: "manual" | "simulated"; score: number | null;
  score_breakdown: { price: number; lead_time: number; rating: number } | null; rank: number | null;
  rationale: string | null; rationale_source: "llm" | "template" | null;
};
export type PO = { id: number; po_number: string; request_id: number; vendor_id: number; vendor_name: string; item: string; quantity: number; unit_price: string; total: string; currency: string; status: string; created_at: string };
export type RequestSummary = { id: number; title: string; item: string; category: string; quantity: number; estimated_unit_price: string; requester: string; status: string; created_at: string };
export type RequestDetail = RequestSummary & { justification: string; recommended_quote_id: number | null; rejection_reason: string | null; approval_threshold_usd: string; score_weights: { price: number; lead_time: number; rating: number }; quotes: Quote[]; purchase_order: PO | null; timeline: Audit[] };
export type InvoiceSummary = { id: number; status: string; filename: string | null; vendor_name: string | null; invoice_number: string | null; po_number: string | null; total: string | null; currency: string | null; confidence: number | null; flags: string[] | null; created_at: string };
export type InvoiceDetail = InvoiceSummary & {
  invoice_date: string | null; line_items: { description: string; qty: string; unit_price: string }[] | null;
  extraction_error: string | null; flag_details: { code: string; message: string }[]; exception_summary: string | null;
  exception_summary_source: "llm" | "template" | null; decision_reason: string | null; purchase_order: PO | null;
  payment: { reference: string; amount: string; currency: string; simulated: boolean; created_at: string } | null;
  raw_text: string | null; timeline: Audit[];
};
export type Dashboard = { open_requests: number; awaiting_approval: number; flagged_invoices: number; spend_this_month_usd: string; avg_cycle_time_hours: number | null; invoices_total: number; touchless_invoices: number; recent_activity: Audit[] };
export type ApprovalItem = { kind: "request" | "invoice"; id: number; title: string; amount_usd: string | null; reason: string; flags: string[]; created_at: string };
export type Health = { status: string; database: string; llm: string; llm_configured: boolean };
