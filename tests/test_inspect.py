import json
from datetime import date
from decimal import Decimal

from boleto_br import arrecadacao, boleto, find_slips, inspect
from boleto_br.__main__ import main

TODAY = date(2026, 11, 20)
SLIP = boleto.build("341", "1090061207727307114005000", Decimal("1250.00"), date(2026, 11, 30))
LINE = SLIP.digitable_line
BILL = arrecadacao.build("3", "6", Decimal("187.43"), "0001000" + "0" * 10 + "000123456782")


def test_valid_bank_slip_line():
    info = inspect(SLIP.formatted_line, reference=TODAY)
    assert info.valid and not info.errors and not info.suggestions
    assert (info.kind, info.input_format) == ("boleto", "digitable_line")
    assert (info.bank_code, info.bank_name, info.currency) == ("341", "Itaú Unibanco", "9")
    assert info.amount == Decimal("1250.00") and info.amount_kind == "fixed"
    assert info.due_date == date(2026, 11, 30)
    assert (info.days_until_due, info.due_status) == (10, "upcoming")
    assert info.barcode == SLIP.barcode and info.digitable_line == LINE


def test_barcode_input_gives_the_same_line():
    info = inspect(SLIP.barcode, reference=TODAY)
    assert info.input_format == "barcode" and info.digitable_line == LINE


def test_due_status():
    assert inspect(LINE, reference=date(2026, 11, 30)).due_status == "due_today"
    late = inspect(LINE, reference=date(2026, 12, 5))
    assert (late.days_until_due, late.due_status) == (-5, "overdue")
    open_slip = inspect(boleto.build("001", "2" * 25).digitable_line, reference=TODAY)
    assert open_slip.due_status == "no_due_date" and open_slip.amount_kind == "open"
    assert open_slip.amount is None


def test_utility_slip_line_and_barcode():
    for code in (BILL.formatted_line, BILL.barcode):
        info = inspect(code)
        assert info.valid and info.kind == "arrecadacao"
        assert info.segment_name == "Energia elétrica e gás"
        assert info.amount == Decimal("187.43") and info.amount_kind == "effective"
        assert info.digitable_line == BILL.digitable_line


def _typo(code, pos):
    return code[:pos] + str((int(code[pos]) + 1) % 10) + code[pos + 1:]


def test_typo_in_field_1_is_located_and_fixable():
    info = inspect(_typo(LINE, 3), reference=TODAY)
    assert not info.valid and info.barcode is None
    assert info.errors[0].code == "check_digit" and 3 in info.errors[0].positions
    assert LINE in info.suggestions
    # fields are still read, for a human to double-check
    assert info.amount == Decimal("1250.00")


def test_missing_extra_and_swapped_digits_are_suggested():
    missing = LINE[:20] + LINE[21:]
    extra = LINE[:5] + "7" + LINE[5:]
    i = next(i for i in range(10, 19) if LINE[i] != LINE[i + 1])   # inside field 2
    swapped = LINE[:i] + LINE[i + 1] + LINE[i] + LINE[i + 2:]
    for bad in (missing, extra, swapped):
        info = inspect(bad, reference=TODAY)
        assert not info.valid and LINE in info.suggestions, bad


def test_swap_in_amount_is_flagged_as_ambiguous():
    # Field 5 (due date + amount) is only guarded by the general digit: many fixes fit.
    i = next(i for i in range(33, 46) if LINE[i] != LINE[i + 1])
    info = inspect(LINE[:i] + LINE[i + 1] + LINE[i] + LINE[i + 2:], reference=TODAY)
    assert not info.valid
    assert any(w.code == "ambiguous_fix" for w in info.warnings)


def test_ambiguous_fixes_are_flagged():
    # A typo in a bare barcode is only guarded by one módulo-11 digit: many codes fit.
    info = inspect(_typo(SLIP.barcode, 20))
    assert not info.valid
    assert any(w.code == "ambiguous_fix" for w in info.warnings)


def test_garbage_does_not_raise():
    info = inspect("abc 123")
    assert not info.valid and info.kind is None and info.errors[0].code == "wrong_length"
    assert info.suggestions == []


def test_to_dict_is_json_ready():
    data = json.loads(json.dumps(inspect(LINE, reference=TODAY).to_dict()))
    assert data["amount"] == "1250.00" and data["due_date"] == "2026-11-30"


def test_find_slips_in_free_text():
    text = (
        "Olá! Segue o boleto de novembro:\n"
        f"{SLIP.formatted_line[:24]}\n{SLIP.formatted_line[24:]}\n"   # wrapped line
        "Vencimento 30/11/2026, valor R$ 1.250,00. Dúvidas: (48) 99999-0000.\n"
        f"Conta de luz: {BILL.formatted_line}\n"
        f"Código de barras: {SLIP.barcode}\n"   # same slip again: reported once
        "CNPJ 11.222.333/0001-81"
    )
    found = find_slips(text, reference=TODAY)
    assert [s.kind for s in found] == ["boleto", "arrecadacao"]
    assert found[0].digitable_line == LINE


def test_find_slips_side_by_side_lines():
    other = boleto.build("237", "9" * 25, Decimal("10"), date(2026, 12, 1)).digitable_line
    assert len(find_slips(LINE + other)) == 2


def test_cli(capsys):
    assert main([SLIP.formatted_line]) == 0
    assert json.loads(capsys.readouterr().out)["bank_code"] == "341"
    assert main(["123"]) == 1
