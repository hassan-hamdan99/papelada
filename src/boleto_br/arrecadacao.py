"""Utility, tax and agreement slips (arrecadação / convênio): 48-digit line, 44-digit barcode.

Barcode layout (FEBRABAN):
    1 product ("8") · 2 segment · 3 value type · 4 general check digit
    5-15 amount (cents) · 16-19 company/agency id (16-23 CNPJ root for segment 6) · rest: free
Value type 6/7 → check digits use módulo 10; 8/9 → módulo 11.
"""
from dataclasses import dataclass
from decimal import Decimal

from ._digits import mod10, mod11_weighted_sum, only_digits

SEGMENTS = {
    "1": "Prefeituras",
    "2": "Saneamento",
    "3": "Energia elétrica e gás",
    "4": "Telecomunicações",
    "5": "Órgãos governamentais",
    "6": "Carnês e assemelhados (identificação por CNPJ)",
    "7": "Multas de trânsito",
    "9": "Uso exclusivo do banco",
}


class InvalidArrecadacao(ValueError):
    pass


def _mod11(digits: str) -> int:
    rest = mod11_weighted_sum(digits) % 11
    return 0 if rest in (0, 1) else 11 - rest


def _dv(digits: str, value_type: str) -> int:
    if value_type in "67":
        return mod10(digits)
    if value_type in "89":
        return _mod11(digits)
    raise InvalidArrecadacao(f"unknown value type: {value_type}")


@dataclass(frozen=True)
class Arrecadacao:
    barcode: str
    digitable_line: str
    segment: str
    segment_name: str | None
    value_type: str
    amount: Decimal | None   # effective amount for types 6 and 8, reference value for 7 and 9
    company_id: str

    @property
    def formatted_line(self) -> str:
        d = self.digitable_line
        return " ".join(f"{d[i:i + 11]}-{d[i + 11]}" for i in range(0, 48, 12))


def barcode_to_line(barcode: str) -> str:
    b = only_digits(barcode)
    blocks = [b[i:i + 11] for i in range(0, 44, 11)]
    return "".join(block + str(_dv(block, b[2])) for block in blocks)


def parse(code: str) -> Arrecadacao:
    d = only_digits(code)
    if len(d) == 48:
        for i in range(0, 48, 12):
            if _dv(d[i:i + 11], d[2]) != int(d[i + 11]):
                raise InvalidArrecadacao(f"wrong check digit in block {i // 12 + 1}")
        barcode = "".join(d[i:i + 11] for i in range(0, 48, 12))
    elif len(d) == 44:
        barcode = d
    else:
        raise InvalidArrecadacao(f"expected 44 or 48 digits, got {len(d)}")
    if barcode[0] != "8":
        raise InvalidArrecadacao("arrecadação codes start with 8")
    if _dv(barcode[:3] + barcode[4:], barcode[2]) != int(barcode[3]):
        raise InvalidArrecadacao("wrong general check digit")

    cents = int(barcode[4:15])
    company = barcode[15:23] if barcode[1] == "6" else barcode[15:19]
    return Arrecadacao(
        barcode=barcode,
        digitable_line=barcode_to_line(barcode),
        segment=barcode[1],
        segment_name=SEGMENTS.get(barcode[1]),
        value_type=barcode[2],
        amount=Decimal(cents) / 100 if cents else None,
        company_id=company,
    )


def is_valid(code: str) -> bool:
    try:
        parse(code)
        return True
    except InvalidArrecadacao:
        return False


def build(segment: str, value_type: str, amount: Decimal, company_and_free: str) -> Arrecadacao:
    """Assemble a valid code. `company_and_free` is positions 16-44 (29 digits)."""
    if len(company_and_free) != 29 or not company_and_free.isdigit():
        raise InvalidArrecadacao("company_and_free needs 29 digits")
    body = f"8{segment}{value_type}{int(amount * 100):011d}{company_and_free}"
    barcode = body[:3] + str(_dv(body, value_type)) + body[3:]
    return parse(barcode)
