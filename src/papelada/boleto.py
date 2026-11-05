"""Bank slips (boleto de cobrança): 47-digit digitable line and 44-digit barcode.

Barcode layout (FEBRABAN):
    1-3 bank · 4 currency (9 = BRL) · 5 general check digit · 6-9 due-date factor
    10-19 amount in cents · 20-44 free field (bank-specific)
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ._digits import mod10, mod11_weighted_sum, only_digits
from .bancos import bank_name

_FIRST_CYCLE_BASE = date(1997, 10, 7)   # factor 0
_RESET = date(2025, 2, 22)              # factor restarts at 1000 on this day
_CYCLE_DAYS = 9000                      # factors 1000..9999


class InvalidBoleto(ValueError):
    pass


def general_check_digit(barcode_without_dv: str) -> int:
    """DV geral (position 5): módulo 11 with weights 2..9; results 0, 10 and 11 become 1."""
    dv = 11 - mod11_weighted_sum(barcode_without_dv) % 11
    return 1 if dv in (0, 10, 11) else dv


def due_date(factor: int, reference: date | None = None) -> date | None:
    """Turn a due-date factor into a date.

    The factor reached 9999 on 2025-02-21 and restarted at 1000 on 2025-02-22, so the same
    factor maps to one date per cycle. The date closest to `reference` (default: today) wins.
    Factor 0 means the slip has no due date.
    """
    if factor == 0:
        return None
    if not 1000 <= factor <= 9999:
        raise InvalidBoleto(f"due-date factor out of range: {factor}")
    reference = reference or date.today()
    candidates = [_FIRST_CYCLE_BASE + timedelta(days=factor)]
    candidates += [_RESET + timedelta(days=factor - 1000 + k * _CYCLE_DAYS) for k in range(3)]
    return min(candidates, key=lambda d: abs((d - reference).days))


def due_date_factor(day: date) -> int:
    if day < date(2000, 7, 3):
        raise InvalidBoleto("dates before 2000-07-03 have no factor")
    if day < _RESET:
        return (day - _FIRST_CYCLE_BASE).days
    return 1000 + (day - _RESET).days % _CYCLE_DAYS


def barcode_to_line(barcode: str) -> str:
    b = only_digits(barcode)
    if len(b) != 44:
        raise InvalidBoleto("barcode must have 44 digits")
    f1 = b[0:4] + b[19:24]
    f2 = b[24:34]
    f3 = b[34:44]
    return f"{f1}{mod10(f1)}{f2}{mod10(f2)}{f3}{mod10(f3)}{b[4]}{b[5:19]}"


def line_to_barcode(line: str) -> str:
    d = only_digits(line)
    if len(d) != 47:
        raise InvalidBoleto("digitable line must have 47 digits")
    return d[0:4] + d[32] + d[33:47] + d[4:9] + d[10:20] + d[21:31]


def format_line(line: str) -> str:
    d = only_digits(line)
    return f"{d[0:5]}.{d[5:10]} {d[10:15]}.{d[15:21]} {d[21:26]}.{d[26:32]} {d[32]} {d[33:47]}"


@dataclass(frozen=True)
class Boleto:
    barcode: str
    digitable_line: str
    bank_code: str
    bank_name: str | None
    currency: str
    amount: Decimal | None          # None when the slip lets the payer fill in the amount
    due_date_factor: int
    due_date: date | None
    free_field: str

    @property
    def formatted_line(self) -> str:
        return format_line(self.digitable_line)


def _check_line_fields(d: str) -> None:
    for start, end, name in ((0, 9, "field 1"), (10, 20, "field 2"), (21, 31, "field 3")):
        if mod10(d[start:end]) != int(d[end]):
            raise InvalidBoleto(f"wrong check digit in {name}")


def parse(code: str, reference: date | None = None) -> Boleto:
    """Parse and validate a digitable line (47 digits) or barcode (44 digits), formatted or not."""
    d = only_digits(code)
    if len(d) == 47:
        _check_line_fields(d)
        barcode = line_to_barcode(d)
    elif len(d) == 44:
        barcode = d
    else:
        raise InvalidBoleto(f"expected 44 or 47 digits, got {len(d)}")
    if barcode[0] == "8":
        raise InvalidBoleto("this is a utility/tax slip (arrecadação); use papelada.arrecadacao")
    if general_check_digit(barcode[:4] + barcode[5:]) != int(barcode[4]):
        raise InvalidBoleto("wrong general check digit")

    factor = int(barcode[5:9])
    cents = int(barcode[9:19])
    return Boleto(
        barcode=barcode,
        digitable_line=barcode_to_line(barcode),
        bank_code=barcode[0:3],
        bank_name=bank_name(barcode[0:3]),
        currency=barcode[3],
        amount=Decimal(cents) / 100 if cents else None,
        due_date_factor=factor,
        due_date=due_date(factor, reference),
        free_field=barcode[19:44],
    )


def is_valid(code: str) -> bool:
    try:
        parse(code)
        return True
    except InvalidBoleto:
        return False


def build(bank_code: str, free_field: str, amount: Decimal | None = None,
          due: date | None = None, currency: str = "9") -> Boleto:
    """Assemble a valid slip from its parts (useful for tests and synthetic data)."""
    if len(bank_code) != 3 or len(free_field) != 25 or not (bank_code + free_field).isdigit():
        raise InvalidBoleto("bank_code needs 3 digits and free_field 25 digits")
    factor = due_date_factor(due) if due else 0
    cents = int((amount or Decimal(0)) * 100)
    body = f"{bank_code}{currency}{factor:04d}{cents:010d}{free_field}"
    barcode = body[:4] + str(general_check_digit(body)) + body[4:]
    return parse(barcode, reference=due)
