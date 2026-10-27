import random
from datetime import date
from decimal import Decimal

import pytest

from boleto_br import boleto, parse_slip
from boleto_br._digits import mod10
from boleto_br.boleto import InvalidBoleto

rng = random.Random(42)


def random_slip(due=date(2026, 11, 20), amount=Decimal("1234.56")):
    free = "".join(rng.choice("0123456789") for _ in range(25))
    return boleto.build(rng.choice(["001", "237", "341", "104", "756"]), free, amount, due)


def test_mod10_reference_value():
    # First field of a Banco do Brasil example line: 00190.00009
    assert mod10("001900000") == 9


@pytest.mark.parametrize("factor,expected", [
    (1000, date(2000, 7, 3)),
    (9999, date(2025, 2, 21)),
])
def test_first_cycle_factor_dates(factor, expected):
    assert boleto.due_date(factor, reference=date(2010, 1, 1)) == expected


def test_factor_reset_of_february_2025():
    assert boleto.due_date_factor(date(2025, 2, 21)) == 9999
    assert boleto.due_date_factor(date(2025, 2, 22)) == 1000
    # factor 1000 means 2025-02-22 for slips issued today, not 2000-07-03
    assert boleto.due_date(1000, reference=date(2025, 3, 1)) == date(2025, 2, 22)


def test_factor_zero_means_no_due_date():
    assert boleto.due_date(0) is None


def test_round_trip_line_and_barcode():
    for _ in range(500):
        slip = random_slip()
        assert len(slip.digitable_line) == 47 and len(slip.barcode) == 44
        assert boleto.line_to_barcode(slip.digitable_line) == slip.barcode
        assert boleto.parse(slip.formatted_line, reference=date(2026, 11, 1)) == slip


def test_parse_extracts_fields():
    slip = boleto.build("341", "1" * 25, Decimal("99.90"), date(2026, 12, 15))
    assert slip.bank_name == "Itaú Unibanco"
    assert slip.amount == Decimal("99.90")
    assert slip.due_date == date(2026, 12, 15)
    assert slip.currency == "9"


def test_open_amount_and_no_due_date():
    slip = boleto.build("001", "2" * 25)
    assert slip.amount is None and slip.due_date is None


def _typo(line, pos):
    return line[:pos] + str((int(line[pos]) + 1) % 10) + line[pos + 1:]


def test_typos_in_fields_1_to_3_are_always_detected():
    # Each of these fields has its own módulo 10 check digit.
    for _ in range(50):
        line = random_slip().digitable_line
        for pos in range(32):
            assert not boleto.is_valid(_typo(line, pos)), f"typo at position {pos} not detected"


def test_typos_in_due_date_and_amount_are_caught_by_the_general_digit_most_of_the_time():
    # FEBRABAN maps general check digits 0, 10 and 11 to 1, so a few single-digit errors in
    # field 5 are undetectable by design. Measure it instead of pretending otherwise.
    caught = total = 0
    for _ in range(300):
        line = random_slip().digitable_line
        for pos in range(33, 47):
            total += 1
            caught += not boleto.is_valid(_typo(line, pos))
    assert caught / total > 0.85


def test_wrong_lengths_and_arrecadacao_are_rejected():
    with pytest.raises(InvalidBoleto):
        boleto.parse("123")
    with pytest.raises(InvalidBoleto, match="arrecadação"):
        boleto.parse("8" * 44)


def test_parse_slip_dispatches_by_prefix():
    assert parse_slip(random_slip().digitable_line).bank_code
