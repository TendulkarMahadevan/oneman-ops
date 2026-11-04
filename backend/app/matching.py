"""Deterministic three-way match (request/PO/invoice). Pure functions: no I/O, no LLM.

Money decisions live here. The LLM never sets a flag, an amount, or a status.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

CENT_TOLERANCE = Decimal("0.02")

FLAG_UNKNOWN_PO = "UNKNOWN_PO"
FLAG_VENDOR_MISMATCH = "VENDOR_MISMATCH"
FLAG_CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
FLAG_PRICE_VARIANCE = "PRICE_VARIANCE"
FLAG_QTY_MISMATCH = "QTY_MISMATCH"
FLAG_TOTAL_MISMATCH = "TOTAL_MISMATCH"
FLAG_DUPLICATE = "DUPLICATE_INVOICE"
FLAG_LOW_CONFIDENCE = "LOW_CONFIDENCE"
FLAG_SUSPICIOUS = "SUSPICIOUS_CONTENT"


@dataclass(frozen=True)
class Line:
    qty: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class InvoiceFacts:
    vendor_name: str
    currency: str
    lines: list[Line]
    total: Decimal
    confidence: float
    suspicious: bool = False


@dataclass(frozen=True)
class PoFacts:
    po_number: str
    vendor_name: str
    quantity: int
    unit_price: Decimal
    currency: str


@dataclass(frozen=True)
class Flag:
    code: str
    message: str


_SUFFIXES = {"inc", "llc", "ltd", "limited", "co", "corp", "corporation", "gmbh", "plc", "company"}


def normalize_vendor(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    while words and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_ref(value: str | None) -> str:
    """Normalise invoice/PO numbers: case- and whitespace/punctuation-insensitive."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above)|disregard (the )?(previous|above|instructions)|"
    r"system prompt|you are (now )?an? (ai|assistant|llm)|as an ai|override|"
    r"(mark|set|approve|pay|release)\b.{0,40}\b(this )?(invoice|payment)\b.{0,30}\b(as )?(matched|approved|paid|clean|urgent)|"
    r"do not (flag|report)|new instructions",
    re.IGNORECASE | re.DOTALL,
)


def looks_like_prompt_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def match(inv: InvoiceFacts, po: PoFacts | None, is_duplicate: bool, price_tolerance_pct: Decimal,
          low_confidence_threshold: float) -> list[Flag]:
    flags: list[Flag] = []

    if po is None:
        flags.append(Flag(FLAG_UNKNOWN_PO, "The invoice does not reference a purchase order that exists in the system."))
    else:
        if normalize_vendor(inv.vendor_name) != normalize_vendor(po.vendor_name):
            flags.append(Flag(FLAG_VENDOR_MISMATCH,
                              f"Invoice vendor differs from the vendor on {po.po_number} ({po.vendor_name})."))
        if inv.currency.upper() != po.currency.upper():
            flags.append(Flag(FLAG_CURRENCY_MISMATCH,
                              f"Invoice currency {inv.currency} differs from PO currency {po.currency}."))

        bad_prices = []
        for i, line in enumerate(inv.lines, start=1):
            pct = (abs(line.unit_price - po.unit_price) / po.unit_price) * 100
            if pct > price_tolerance_pct:
                signed = (line.unit_price - po.unit_price) / po.unit_price * 100
                bad_prices.append(f"line {i} unit price {_fmt(line.unit_price)} vs PO {_fmt(po.unit_price)} "
                                  f"({signed:+.1f}%)")
        if bad_prices:
            flags.append(Flag(FLAG_PRICE_VARIANCE,
                              f"Unit price outside the {price_tolerance_pct}% tolerance: " + "; ".join(bad_prices) + "."))

        invoiced_qty = sum((ln.qty for ln in inv.lines), Decimal(0))
        if invoiced_qty != po.quantity:
            flags.append(Flag(FLAG_QTY_MISMATCH,
                              f"Invoiced quantity {invoiced_qty.normalize():f} differs from PO quantity {po.quantity}."))

    computed = sum((ln.qty * ln.unit_price for ln in inv.lines), Decimal(0))
    if abs(computed - inv.total) > CENT_TOLERANCE:
        flags.append(Flag(FLAG_TOTAL_MISMATCH,
                          f"Stated total {_fmt(inv.total)} does not equal the sum of its lines {_fmt(computed)}."))

    if is_duplicate:
        flags.append(Flag(FLAG_DUPLICATE, "An invoice with the same vendor and invoice number was already received."))

    if inv.confidence < low_confidence_threshold:
        flags.append(Flag(FLAG_LOW_CONFIDENCE,
                          f"Extraction confidence {inv.confidence:.2f} is below the {low_confidence_threshold:.2f} threshold."))

    if inv.suspicious:
        flags.append(Flag(FLAG_SUSPICIOUS,
                          "The document contains text that looks like instructions to an AI system. It was treated as data only."))
    return flags


SUGGESTED_ACTIONS = {
    FLAG_UNKNOWN_PO: "Ask the vendor for the correct PO number, or reject if no order was placed.",
    FLAG_VENDOR_MISMATCH: "Verify the remit-to vendor before paying; this can indicate a fraudulent invoice.",
    FLAG_CURRENCY_MISMATCH: "Confirm the agreed currency with the vendor and request a corrected invoice.",
    FLAG_PRICE_VARIANCE: "Compare against the quote; request a credit note or corrected invoice.",
    FLAG_QTY_MISMATCH: "Check the goods-received record; pay only for what was delivered.",
    FLAG_TOTAL_MISMATCH: "Request a corrected invoice; the arithmetic on the document is inconsistent.",
    FLAG_DUPLICATE: "Reject as a duplicate unless the vendor confirms it is a distinct billing.",
    FLAG_LOW_CONFIDENCE: "Read the original document and confirm the extracted fields manually.",
    FLAG_SUSPICIOUS: "Review the original document; do not rely on its contents without checking.",
}
