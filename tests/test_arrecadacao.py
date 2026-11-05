import random
from decimal import Decimal

import pytest

from papelada import arrecadacao, parse_slip
from papelada.arrecadacao import InvalidArrecadacao

rng = random.Random(7)


def random_code(value_type):
    rest = "".join(rng.choice("0123456789") for _ in range(29))
    return arrecadacao.build(rng.choice("12345"), value_type, Decimal("187.43"), rest)


@pytest.mark.parametrize("value_type", ["6", "7", "8", "9"])
def test_round_trip_for_mod10_and_mod11(value_type):
    for _ in range(200):
        code = random_code(value_type)
        assert len(code.digitable_line) == 48
        assert arrecadacao.parse(code.formatted_line) == code


def test_fields():
    code = arrecadacao.build("3", "6", Decimal("187.43"), "0" * 29)
    assert code.segment_name == "Energia elétrica e gás"
    assert code.amount == Decimal("187.43")


@pytest.mark.parametrize("value_type", ["6", "8"])
def test_single_digit_typos_are_detected(value_type):
    line = random_code(value_type).digitable_line
    for pos in range(48):
        typo = line[:pos] + str((int(line[pos]) + 1) % 10) + line[pos + 1:]
        assert not arrecadacao.is_valid(typo)


def test_must_start_with_8():
    with pytest.raises(InvalidArrecadacao):
        arrecadacao.parse("1" * 44)


def test_parse_slip_routes_utility_codes():
    assert parse_slip(random_code("6").digitable_line).segment
