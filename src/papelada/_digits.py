"""Check-digit algorithms shared by the FEBRABAN and Receita Federal formats."""
import re

_NON_DIGIT = re.compile(r"\D")


def only_digits(value: str) -> str:
    return _NON_DIGIT.sub("", value or "")


def mod10(digits: str) -> int:
    """Módulo 10: weights 2,1,2,1... from the right; two-digit products are summed digit by digit."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        product = int(ch) * (2 if i % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    return (10 - total % 10) % 10


def mod11_weighted_sum(digits: str, max_weight: int = 9) -> int:
    """Sum with weights 2..max_weight cycling from the right."""
    return sum(int(ch) * (2 + i % (max_weight - 1)) for i, ch in enumerate(reversed(digits)))
