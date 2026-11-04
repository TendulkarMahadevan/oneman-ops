from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def line_total(qty: int | Decimal, unit_price: Decimal) -> Decimal:
    return (Decimal(qty) * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
