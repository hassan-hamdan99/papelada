"""NF-e XML reader. Every document here is synthetic: made-up companies, valid check digits."""
import json
from datetime import date
from decimal import Decimal

import pytest

from papelada import nfe, nfe_xml
from papelada.documentos import cnpj_check_digits, cpf_check_digits

ISSUER = "112223330001" + cnpj_check_digits("112223330001")
ALNUM_ISSUER = "12ABC34501DE" + cnpj_check_digits("12ABC34501DE")
BUYER_CPF = "123456789" + cpf_check_digits("123456789")


def make_key(issuer=ISSUER, model="55", number=12345):
    first43 = f"4226 10{issuer}{model}001{number:09d}112345678".replace(" ", "")
    return first43 + str(nfe.check_digit(first43))


ITEM = """
<det nItem="{n}">
  <prod><cProd>P-{n}</cProd><cEAN>SEM GTIN</cEAN><xProd>Parafuso sextavado {n}</xProd>
    <NCM>73181500</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>10.0000</qCom>
    <vUnCom>5.0000000000</vUnCom><vProd>50.00</vProd><indTot>1</indTot></prod>
  <imposto><vTotTrib>6.50</vTotTrib>
    <ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>50.00</vBC>
      <pICMS>17.00</pICMS><vICMS>8.50</vICMS></ICMS00></ICMS>
    <PIS><PISAliq><CST>01</CST><vBC>50.00</vBC><pPIS>1.65</pPIS><vPIS>0.83</vPIS></PISAliq></PIS>
    <IBSCBS><CST>000</CST><gIBSCBS><vBC>50.00</vBC><gCBS><pCBS>0.90</pCBS><vCBS>0.45</vCBS></gCBS>
    </gIBSCBS></IBSCBS>
  </imposto>
</det>"""


def make_xml(key=None, issuer=ISSUER, items=2, v_nf="100.00", status="100", tp_amb="1",
             dups=(("001", "2026-11-15", "50.00"), ("002", "2026-12-15", "50.00")),
             protocol=True, model="55"):
    key = key or make_key(issuer, model)
    dup_xml = "".join(f"<dup><nDup>{n}</nDup><dVenc>{d}</dVenc><vDup>{v}</vDup></dup>"
                      for n, d, v in dups)
    nfe_el = f"""<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
 <infNFe versao="4.00" Id="NFe{key}">
  <ide><cUF>42</cUF><cNF>12345678</cNF><natOp>Venda de mercadoria</natOp><mod>{model}</mod>
   <serie>1</serie><nNF>12345</nNF><dhEmi>2026-10-15T10:30:00-03:00</dhEmi><tpNF>1</tpNF>
   <tpAmb>{tp_amb}</tpAmb><finNFe>1</finNFe></ide>
  <emit><CNPJ>{issuer}</CNPJ><xNome>Ferragens Exemplo Ltda</xNome><xFant>Ferragens Exemplo</xFant>
   <enderEmit><xLgr>Rua das Flores</xLgr><nro>100</nro><xBairro>Centro</xBairro>
    <cMun>4205407</cMun><xMun>Florianopolis</xMun><UF>SC</UF><CEP>88000000</CEP></enderEmit>
   <IE>123456789</IE><CRT>3</CRT></emit>
  <dest><CPF>{BUYER_CPF}</CPF><xNome>Cliente Exemplo</xNome><email>cliente@example.com</email></dest>
  {"".join(ITEM.format(n=i + 1) for i in range(items))}
  <total><ICMSTot><vBC>100.00</vBC><vICMS>17.00</vICMS><vICMSDeson>0.00</vICMSDeson>
   <vST>0.00</vST><vFCPST>0.00</vFCPST><vProd>100.00</vProd><vFrete>0.00</vFrete>
   <vSeg>0.00</vSeg><vDesc>0.00</vDesc><vII>0.00</vII><vIPI>0.00</vIPI><vIPIDevol>0.00</vIPIDevol>
   <vPIS>1.66</vPIS><vCOFINS>7.60</vCOFINS><vOutro>0.00</vOutro><vNF>{v_nf}</vNF>
   <vTotTrib>13.00</vTotTrib></ICMSTot></total>
  <transp><modFrete>9</modFrete></transp>
  <cobr><fat><nFat>12345</nFat><vOrig>100.00</vOrig><vDesc>0.00</vDesc><vLiq>100.00</vLiq></fat>
   {dup_xml}</cobr>
  <pag><detPag><tPag>15</tPag><vPag>100.00</vPag></detPag></pag>
  <infAdic><infCpl>Pedido 987</infCpl></infAdic>
 </infNFe>
 <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><SignedInfo/></Signature>
</NFe>"""
    if not protocol:
        return nfe_el
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">{nfe_el}
 <protNFe versao="4.00"><infProt><tpAmb>{tp_amb}</tpAmb><chNFe>{key}</chNFe>
  <dhRecbto>2026-10-15T10:31:02-03:00</dhRecbto><nProt>142260000012345</nProt>
  <cStat>{status}</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>
</nfeProc>"""


def test_authorized_nfe_is_read_completely():
    doc = nfe_xml.parse(make_xml())
    assert doc.valid and doc.authorized and doc.signed, doc.errors
    assert doc.warnings == []
    assert (doc.model_name, doc.series, doc.number) == ("NF-e", 1, 12345)
    assert doc.operation == "saída" and doc.environment == "production"
    assert doc.issuer.name == "Ferragens Exemplo Ltda" and doc.issuer.tax_regime == "Regime Normal"
    assert doc.issuer.address.city == "Florianopolis"
    assert doc.recipient.document_type == "cpf"
    assert doc.totals.total == Decimal("100.00") and doc.totals.icms == Decimal("17.00")
    assert [i.due_date for i in doc.installments] == [date(2026, 11, 15), date(2026, 12, 15)]
    assert doc.payments[0].method == "Boleto bancário"
    assert doc.protocol.number == "142260000012345"


def test_items_and_generic_tax_groups():
    item = nfe_xml.parse(make_xml()).items[0]
    assert (item.number, item.ncm, item.cfop, item.ean) == (1, "73181500", "5102", None)
    assert item.quantity == Decimal("10") and item.total == Decimal("50.00")
    assert item.taxes["ICMS"]["CST"] == "00" and item.taxes["ICMS"]["vICMS"] == Decimal("8.50")
    # Tax reform groups come through without special code
    assert item.taxes["IBSCBS"]["vCBS"] == Decimal("0.45")


def test_bare_nfe_without_protocol_or_from_file(tmp_path):
    doc = nfe_xml.parse(make_xml(protocol=False))
    assert doc.valid and not doc.authorized
    assert [w.code for w in doc.warnings] == ["no_protocol"]
    path = tmp_path / "nota.xml"
    path.write_text(make_xml(), encoding="utf-8")
    assert nfe_xml.parse(path).number == 12345 and nfe_xml.parse(str(path)).valid


def test_alphanumeric_cnpj_issuer():
    doc = nfe_xml.parse(make_xml(issuer=ALNUM_ISSUER))
    assert doc.valid, doc.errors
    assert nfe.parse_key(doc.key).issuer == ALNUM_ISSUER


def test_nfce_model_65():
    assert nfe_xml.parse(make_xml(model="65")).model_name == "NFC-e"


def test_contradictions_are_errors():
    other_key = make_key(number=99999)
    errors = [e.code for e in nfe_xml.parse(make_xml(key=other_key)).errors]
    assert "key_mismatch" in errors
    bad = make_key()[:-1] + str((int(make_key()[-1]) + 1) % 10)
    assert "access_key" in [e.code for e in nfe_xml.parse(make_xml(key=bad)).errors]
    assert "totals" in [e.code for e in nfe_xml.parse(make_xml(items=3)).errors]


def test_denied_and_homologation():
    denied = nfe_xml.parse(make_xml(status="302"))
    assert not denied.authorized and "not_authorized" in [e.code for e in denied.errors]
    test_env = nfe_xml.parse(make_xml(tp_amb="2"))
    assert "homologation" in [w.code for w in test_env.warnings]


def test_arithmetic_warnings():
    doc = nfe_xml.parse(make_xml(v_nf="120.00", dups=(("001", "2026-11-15", "40.00"),)))
    codes = {w.code for w in doc.warnings}
    assert {"total_formula", "installments", "payments"} <= codes


def test_not_an_nfe():
    with pytest.raises(nfe_xml.InvalidNFeXML, match="event"):
        nfe_xml.parse('<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe"/>')
    with pytest.raises(nfe_xml.InvalidNFeXML, match="infNFe"):
        nfe_xml.parse("<html/>")
    with pytest.raises(nfe_xml.InvalidNFeXML, match="well-formed"):
        nfe_xml.parse("<NFe><infNFe>")


def test_dtd_is_refused():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><NFe>&a;</NFe>'
    with pytest.raises(nfe_xml.InvalidNFeXML, match="DTD"):
        nfe_xml.parse(bomb)


def test_to_dict_is_json_ready():
    data = json.loads(json.dumps(nfe_xml.parse(make_xml()).to_dict()))
    assert data["totals"]["total"] == "100.00" and data["authorized"] is True
    assert data["installments"][0]["due_date"] == "2026-11-15"


def test_cli_reads_xml(tmp_path, capsys):
    from papelada.__main__ import main

    path = tmp_path / "nota.xml"
    path.write_text(make_xml(), encoding="utf-8")
    assert main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["total"] == "100.00"
