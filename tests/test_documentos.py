import random

import pytest

from boleto_br import documentos as d

rng = random.Random(3)


@pytest.mark.parametrize("cpf", ["529.982.247-25", "11144477735"])
def test_valid_cpfs(cpf):
    assert d.is_valid_cpf(cpf)


@pytest.mark.parametrize("cpf", ["529.982.247-24", "111.111.111-11", "123", ""])
def test_invalid_cpfs(cpf):
    assert not d.is_valid_cpf(cpf)


def test_numeric_cnpj():
    assert d.is_valid_cnpj("11.222.333/0001-81")
    assert not d.is_valid_cnpj("11.222.333/0001-80")
    assert not d.is_valid_cnpj("00000000000000")


def test_alphanumeric_cnpj_official_example():
    # Example published by Receita Federal for the alphanumeric CNPJ
    assert d.cnpj_check_digits("12ABC34501DE") == "35"
    assert d.is_valid_cnpj("12.ABC.345/01DE-35")
    assert d.is_valid_cnpj("12abc34501de35")       # case-insensitive
    assert d.is_alphanumeric_cnpj("12.ABC.345/01DE-35")
    assert not d.is_alphanumeric_cnpj("11.222.333/0001-81")


def test_alphanumeric_check_digits_are_numeric():
    assert not d.is_valid_cnpj("12ABC34501DE3A")


def test_generated_documents_validate():
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for _ in range(300):
        base = "".join(rng.choice(chars) for _ in range(12))
        cnpj = base + d.cnpj_check_digits(base)
        assert d.is_valid_cnpj(d.format_cnpj(cnpj))
        cpf9 = "".join(rng.choice("0123456789") for _ in range(9))
        cpf = cpf9 + d.cpf_check_digits(cpf9)
        if cpf != cpf[0] * 11:
            assert d.is_valid_cpf(d.format_cpf(cpf))


def test_formatting():
    assert d.format_cpf("52998224725") == "529.982.247-25"
    assert d.format_cnpj("12abc34501de35") == "12.ABC.345/01DE-35"
