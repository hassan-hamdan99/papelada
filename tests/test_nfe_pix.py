from decimal import Decimal

import pytest

from papelada import nfe, pix
from papelada.documentos import cnpj_check_digits

# --- NF-e access key (synthetic) ------------------------------------------------

ISSUER = "112223330001" + cnpj_check_digits("112223330001")


def make_key(uf="42", aamm="2610", model="55", series="001", number="000012345", tp="1", code="12345678"):
    first43 = f"{uf}{aamm}{ISSUER}{model}{series}{number}{tp}{code}"
    return first43 + str(nfe.check_digit(first43))


def test_parse_key_fields():
    k = nfe.parse_key(make_key())
    assert (k.uf, k.year, k.month) == ("SC", 2026, 10)
    assert k.model_name == "NF-e" and k.series == 1 and k.number == 12345
    assert k.issuer_is_valid
    assert k.formatted.count(" ") == 10


def test_key_typos_are_detected():
    key = make_key()
    for pos in range(44):
        typo = key[:pos] + str((int(key[pos]) + 1) % 10) + key[pos + 1:]
        assert not nfe.is_valid_key(typo)


def test_key_with_bad_month_or_uf():
    with pytest.raises(nfe.InvalidAccessKey):
        nfe.parse_key(make_key(aamm="2613"))
    with pytest.raises(nfe.InvalidAccessKey):
        nfe.parse_key(make_key(uf="99"))


# --- Pix ---------------------------------------------------------------------------

# Example from the Central Bank's BR Code manual
BCB_EXAMPLE = (
    "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-426655440000"
    "5204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D"
)


def test_crc16_check_value():
    assert pix.crc16("123456789") == "29B1"


def test_parse_official_example():
    code = pix.parse(BCB_EXAMPLE)
    assert code.key == "123e4567-e12b-12d1-a456-426655440000"
    assert code.key_type == "evp"
    assert (code.merchant_name, code.merchant_city) == ("Fulano de Tal", "BRASILIA")
    assert code.txid is None and code.amount is None and not code.is_dynamic


def test_build_reproduces_official_example():
    assert pix.build("123e4567-e12b-12d1-a456-426655440000", "Fulano de Tal", "BRASILIA") == BCB_EXAMPLE


def test_build_with_amount_and_txid_round_trips():
    payload = pix.build("+5548999990000", "Loja Exemplo", "FLORIANOPOLIS", Decimal("49.9"), txid="PEDIDO123")
    code = pix.parse(payload)
    assert code.amount == Decimal("49.90") and code.txid == "PEDIDO123" and code.key_type == "phone"


def test_tampered_code_fails_crc():
    tampered = BCB_EXAMPLE.replace("Fulano", "Fulana")
    with pytest.raises(pix.InvalidPix, match="CRC"):
        pix.parse(tampered)


@pytest.mark.parametrize("key,kind", [
    ("52998224725", "cpf"), ("11222333000181", "cnpj"), ("pix@example.com", "email"),
    ("+5548999990000", "phone"), ("123e4567-e12b-12d1-a456-426655440000", "evp"), ("???", "unknown"),
])
def test_key_types(key, kind):
    assert pix.key_type(key) == kind
