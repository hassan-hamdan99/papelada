"""Everything a slip code can tell you, in one call: `inspect()` and `find_slips()`.

`inspect()` never raises on bad input. It reports what kind of code it is, every problem it
found (with positions), the fields it could read, and, when the code is invalid, the valid codes
that are one typo away. That last part is meant for OCR and LLM extraction: if exactly one valid
code is one edit away, it is very likely what the document says; if several are, ask a person.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from . import arrecadacao, boleto
from ._digits import mod10, only_digits
from .bancos import bank_name

MAX_SUGGESTIONS = 5
_LINE_FIELDS = ((0, 9, "field 1"), (10, 20, "field 2"), (21, 31, "field 3"))


@dataclass(frozen=True)
class Problem:
    code: str                         # machine-readable: wrong_length, check_digit, ...
    message: str
    positions: tuple[int, ...] = ()   # 0-based, in the digits of the input


@dataclass
class SlipInfo:
    input: str
    digits: str
    kind: str | None                  # "boleto" | "arrecadacao" | None (unrecognized)
    input_format: str | None          # "digitable_line" | "barcode" | None
    valid: bool
    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)   # valid codes one edit away

    # Normalized forms: only filled in when the code is valid.
    barcode: str | None = None
    digitable_line: str | None = None
    formatted_line: str | None = None

    # Read from the layout even when a check digit fails. Only trust them when `valid`.
    amount: Decimal | None = None
    amount_kind: str | None = None    # boleto: fixed | open · arrecadação: effective | reference
    due_date: date | None = None
    days_until_due: int | None = None
    due_status: str | None = None     # upcoming | due_today | overdue | no_due_date
    bank_code: str | None = None
    bank_name: str | None = None
    currency: str | None = None
    free_field: str | None = None
    segment: str | None = None
    segment_name: str | None = None
    value_type: str | None = None
    company_id: str | None = None

    def to_dict(self) -> dict:
        """JSON-ready dict: amounts as strings ("125.00"), dates as ISO strings."""
        out = asdict(self)
        if self.amount is not None:
            out["amount"] = str(self.amount)
        if self.due_date is not None:
            out["due_date"] = self.due_date.isoformat()
        return out


def _classify(d: str) -> tuple[str | None, str | None]:
    n = len(d)
    if n == 48 and d[0] == "8":
        return "arrecadacao", "digitable_line"
    if n == 47:
        return "boleto", "digitable_line"
    if n == 44:
        return ("arrecadacao" if d[0] == "8" else "boleto"), "barcode"
    return None, None


def _check(d: str) -> tuple[str | None, str | None, str | None, list[Problem]]:
    """Structure and check digits only. Returns (kind, input_format, barcode, errors)."""
    kind, fmt = _classify(d)
    if kind is None:
        if len(d) == 48:
            msg = ("48 digits but it doesn't start with 8, so it isn't a utility/tax line; "
                   "a bank slip line has 47 digits (one digit too many?)")
        else:
            msg = ("expected 47 digits (bank slip line), 48 (utility/tax line) or 44 (barcode), "
                   f"got {len(d)}")
        return None, None, None, [Problem("wrong_length", msg)]

    errors: list[Problem] = []
    if kind == "boleto":
        if fmt == "digitable_line":
            for start, end, name in _LINE_FIELDS:
                if mod10(d[start:end]) != int(d[end]):
                    errors.append(Problem("check_digit", f"wrong check digit in {name}",
                                          tuple(range(start, end + 1))))
            barcode = boleto.line_to_barcode(d)
            if d[0] == "8":
                errors.append(Problem("wrong_length", "starts with 8 like a utility/tax line, "
                                      "but has 47 digits instead of 48", ()))
        else:
            barcode = d
        if boleto.general_check_digit(barcode[:4] + barcode[5:]) != int(barcode[4]):
            pos = 32 if fmt == "digitable_line" else 4
            errors.append(Problem("check_digit", "wrong general check digit: a digit of the "
                                  "amount, due date or free field is probably wrong", (pos,)))
        factor = int(barcode[5:9])
        if 0 < factor < 1000:
            pos = 33 if fmt == "digitable_line" else 5
            errors.append(Problem("due_date_factor", f"due-date factor {factor} is not used "
                                  "(valid: 0 or 1000-9999)", tuple(range(pos, pos + 4))))
        return kind, fmt, barcode, errors

    value_type = d[2]
    if value_type not in "6789":
        errors.append(Problem("value_type", f"unknown value type {value_type} (expected 6, 7, 8 or 9)",
                              (2,)))
        return kind, fmt, None, errors
    if fmt == "digitable_line":
        for i in range(0, 48, 12):
            if arrecadacao._dv(d[i:i + 11], value_type) != int(d[i + 11]):
                errors.append(Problem("check_digit", f"wrong check digit in block {i // 12 + 1}",
                                      tuple(range(i, i + 12))))
        barcode = "".join(d[i:i + 11] for i in range(0, 48, 12))
    else:
        barcode = d
    if arrecadacao._dv(barcode[:3] + barcode[4:], value_type) != int(barcode[3]):
        errors.append(Problem("check_digit", "wrong general check digit", (3,)))
    return kind, fmt, barcode, errors


def _is_valid(d: str) -> bool:
    return not _check(d)[3]


def _one_edit_away(d: str):
    """Substitutions, adjacent swaps, one missing digit, one extra digit."""
    digits = "0123456789"
    for i, c in enumerate(d):
        for x in digits:
            if x != c:
                yield d[:i] + x + d[i + 1:]
    for i in range(len(d) - 1):
        if d[i] != d[i + 1]:
            yield d[:i] + d[i + 1] + d[i] + d[i + 2:]
    if len(d) < 48:
        for i in range(len(d) + 1):
            for x in digits:
                yield d[:i] + x + d[i:]
    if len(d) > 44:
        for i in range(len(d)):
            yield d[:i] + d[i + 1:]


def _suggest(d: str) -> list[str]:
    if not 43 <= len(d) <= 49:
        return []
    seen: dict[str, None] = {}
    for candidate in _one_edit_away(d):
        if candidate not in seen and _is_valid(candidate):
            seen[candidate] = None
    return list(seen)


def _due_status(due: date | None, today: date) -> tuple[int | None, str]:
    if due is None:
        return None, "no_due_date"
    days = (due - today).days
    return days, "upcoming" if days > 0 else "due_today" if days == 0 else "overdue"


def inspect(code: str, reference: date | None = None) -> SlipInfo:
    """Read everything possible from a bank slip or utility/tax slip, valid or not.

    Accepts the digitable line (47 or 48 digits) or the barcode (44), with or without dots,
    spaces and hyphens. `reference` is "today" for due-date math (default: date.today()).
    """
    today = reference or date.today()
    d = only_digits(code)
    kind, fmt, barcode, errors = _check(d)
    info = SlipInfo(input=code, digits=d, kind=kind, input_format=fmt, valid=not errors,
                    errors=errors)

    if errors:
        found = _suggest(d)
        if len(found) > MAX_SUGGESTIONS:
            # Never return a truncated list: it may leave out the right code.
            info.warnings.append(Problem("ambiguous_fix", f"{len(found)} valid codes are one edit "
                                         "away; too many to suggest, ask for the code again"))
        else:
            info.suggestions = found
            if len(found) > 1:
                info.warnings.append(Problem("ambiguous_fix", f"{len(found)} valid codes are one "
                                             "edit away; don't auto-correct, let a person pick"))

    if barcode is None:
        return info

    if kind == "boleto":
        cents = int(barcode[9:19])
        factor = int(barcode[5:9])
        try:
            info.due_date = boleto.due_date(factor, today)
        except boleto.InvalidBoleto:
            info.due_date = None
        info.days_until_due, info.due_status = _due_status(info.due_date, today)
        info.amount = Decimal(cents).scaleb(-2) if cents else None
        info.amount_kind = "fixed" if cents else "open"
        info.bank_code = barcode[:3]
        info.bank_name = bank_name(info.bank_code)
        info.currency = barcode[3]
        info.free_field = barcode[19:]
        if info.currency != "9":
            info.warnings.append(Problem("currency", f"currency code {info.currency} is not "
                                         "BRL (9)", ()))
        if info.bank_name is None:
            info.warnings.append(Problem("unknown_bank", f"bank {info.bank_code} is not in the "
                                         "built-in list", ()))
        if info.valid:
            info.barcode = barcode
            info.digitable_line = boleto.barcode_to_line(barcode)
            info.formatted_line = boleto.format_line(info.digitable_line)
    else:
        cents = int(barcode[4:15])
        info.segment = barcode[1]
        info.segment_name = arrecadacao.SEGMENTS.get(info.segment)
        info.value_type = barcode[2]
        info.amount = Decimal(cents).scaleb(-2) if cents else None
        info.amount_kind = "effective" if info.value_type in "68" else "reference"
        info.company_id = barcode[15:23] if info.segment == "6" else barcode[15:19]
        info.free_field = barcode[23:] if info.segment == "6" else barcode[19:]
        if info.amount_kind == "reference":
            info.warnings.append(Problem("reference_value", "value types 7 and 9 carry a "
                                         "reference value (e.g. an index), not an amount in BRL",
                                         ()))
        if info.valid:
            slip = arrecadacao.parse(barcode)
            info.barcode = barcode
            info.digitable_line = slip.digitable_line
            info.formatted_line = slip.formatted_line
    return info


# Digits separated by at most 3 dots, spaces, hyphens or line breaks: catches lines that are
# formatted or wrapped in e-mails and PDF text, but not numbers separated by words.
_RUN = re.compile(r"\d(?:[ .\-\t\r\n]{0,3}\d)+")


def find_slips(text: str, reference: date | None = None) -> list[SlipInfo]:
    """Find every valid slip code in free text (an e-mail, PDF text, a chat message).

    Digitable lines are found anywhere in a run of digits, so two lines pasted side by side
    both come out. A bare 44-digit barcode only counts when it is the whole run: its single
    check digit would let too many random numbers through. Duplicates (the same slip as line
    and barcode) are returned once.
    """
    results: list[SlipInfo] = []
    seen: set[str] = set()
    for match in _RUN.finditer(text):
        d = only_digits(match.group())
        hits: list[str] = []
        if len(d) == 44 and _is_valid(d):
            hits.append(d)
        i = 0
        while i <= len(d) - 47:
            for n in (48, 47):
                if i + n <= len(d) and _is_valid(d[i:i + n]):
                    hits.append(d[i:i + n])
                    i += n
                    break
            else:
                i += 1
        for hit in hits:
            info = inspect(hit, reference)
            if info.barcode not in seen:
                seen.add(info.barcode)
                results.append(info)
    return results
