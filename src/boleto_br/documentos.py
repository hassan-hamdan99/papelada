"""CPF and CNPJ validation and formatting, including the alphanumeric CNPJ.

Since July 2026 new CNPJs may use letters in the first 12 positions. Each character counts
as its ASCII code minus 48 ("0"-"9" -> 0-9, "A" -> 17 ... "Z" -> 42), so the same algorithm
validates both numeric and alphanumeric CNPJs. The two check digits are always numeric.
"""
import re

_CNPJ_CLEAN = re.compile(r"[^0-9A-Za-z]")


def _dv(values: list[int], weights: list[int]) -> int:
    rest = sum(v * w for v, w in zip(values, weights)) % 11
    return 0 if rest < 2 else 11 - rest


# --- CPF -------------------------------------------------------------------

def clean_cpf(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def cpf_check_digits(first9: str) -> str:
    nums = [int(c) for c in first9]
    d1 = _dv(nums, list(range(10, 1, -1)))
    d2 = _dv(nums + [d1], list(range(11, 1, -1)))
    return f"{d1}{d2}"


def is_valid_cpf(value: str) -> bool:
    cpf = clean_cpf(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    return cpf_check_digits(cpf[:9]) == cpf[9:]


def format_cpf(value: str) -> str:
    c = clean_cpf(value)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


# --- CNPJ ------------------------------------------------------------------

def clean_cnpj(value: str) -> str:
    return _CNPJ_CLEAN.sub("", value or "").upper()


def cnpj_check_digits(first12: str) -> str:
    vals = [ord(c) - 48 for c in first12.upper()]
    d1 = _dv(vals, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _dv(vals + [d1], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return f"{d1}{d2}"


def is_valid_cnpj(value: str) -> bool:
    cnpj = clean_cnpj(value)
    if len(cnpj) != 14 or not re.fullmatch(r"[0-9A-Z]{12}\d{2}", cnpj):
        return False
    if cnpj == cnpj[0] * 14:
        return False
    return cnpj_check_digits(cnpj[:12]) == cnpj[12:]


def is_alphanumeric_cnpj(value: str) -> bool:
    return is_valid_cnpj(value) and not clean_cnpj(value).isdigit()


def format_cnpj(value: str) -> str:
    c = clean_cnpj(value)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
