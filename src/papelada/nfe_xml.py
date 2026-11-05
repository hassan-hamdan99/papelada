"""Read NF-e and NFC-e XML (layout 4.00): parties, items, taxes, totals, installments, payments
and the authorization protocol, then cross-check what the document says about itself.

    from papelada import nfe_xml
    doc = nfe_xml.parse("35261011222333000181550010000123451123456789-procNFe.xml")
    doc.issuer.name, doc.totals.total, doc.installments, doc.authorized

Standard library only. Like `inspect()`, it reports problems instead of stopping at the first:
`doc.errors` (the document contradicts itself or isn't authorized) and `doc.warnings`
(worth a look). What it does not do: verify the XML-DSig signature or query SEFAZ.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from . import nfe
from ._inspect import Problem
from .documentos import is_valid_cnpj, is_valid_cpf

CRT = {"1": "Simples Nacional", "2": "Simples Nacional, excesso de sublimite",
       "3": "Regime Normal", "4": "MEI"}
PURPOSE = {"1": "normal", "2": "complementar", "3": "ajuste", "4": "devolução"}
FREIGHT = {"0": "emitente (CIF)", "1": "destinatário (FOB)", "2": "terceiros",
           "3": "próprio remetente", "4": "próprio destinatário", "9": "sem frete"}
PAYMENT_METHODS = {
    "01": "Dinheiro", "02": "Cheque", "03": "Cartão de crédito", "04": "Cartão de débito",
    "05": "Crédito loja", "10": "Vale alimentação", "11": "Vale refeição", "12": "Vale presente",
    "13": "Vale combustível", "14": "Duplicata mercantil", "15": "Boleto bancário",
    "16": "Depósito bancário", "17": "Pix", "18": "Transferência / carteira digital",
    "19": "Fidelidade / cashback", "20": "Pix estático", "90": "Sem pagamento", "99": "Outros",
}
AUTHORIZED = {"100", "150"}   # 150: authorized out of time

# Leaf tags that hold amounts, rates or quantities: vBC, vICMS, pICMS, qCom, vUnCom...
_NUMERIC_TAG = re.compile(r"^[vpq][A-Z]")


class InvalidNFeXML(ValueError):
    pass


@dataclass
class Address:
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    district: str | None = None
    city: str | None = None
    city_code: str | None = None
    uf: str | None = None
    zip_code: str | None = None
    country: str | None = None
    phone: str | None = None


@dataclass
class Party:
    document: str | None            # CNPJ (maybe alphanumeric), CPF or foreign id
    document_type: str | None       # cnpj | cpf | foreign
    name: str | None
    trade_name: str | None = None
    state_registration: str | None = None   # IE
    tax_regime: str | None = None           # CRT, issuer only
    email: str | None = None
    address: Address | None = None


@dataclass
class Item:
    number: int
    code: str | None
    description: str | None
    ncm: str | None
    cfop: str | None
    unit: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    total: Decimal | None
    discount: Decimal | None = None
    ean: str | None = None
    cest: str | None = None
    # Every tax group as found: {"ICMS": {"orig": "0", "CST": "00", "vBC": Decimal(...)}, ...}.
    # Kept generic on purpose, so new groups (e.g. IBS/CBS of the tax reform) come through.
    taxes: dict = field(default_factory=dict)
    additional_info: str | None = None


@dataclass
class Totals:
    products: Decimal | None
    discount: Decimal | None
    freight: Decimal | None
    insurance: Decimal | None
    other: Decimal | None
    icms: Decimal | None
    icms_st: Decimal | None
    ipi: Decimal | None
    pis: Decimal | None
    cofins: Decimal | None
    approximate_taxes: Decimal | None   # vTotTrib, the "Lei da Transparência" estimate
    total: Decimal | None               # vNF
    raw: dict = field(default_factory=dict)   # every tag of every total group


@dataclass
class Installment:
    number: str | None
    due_date: date | None
    amount: Decimal | None


@dataclass
class Payment:
    method_code: str | None
    method: str | None
    amount: Decimal | None


@dataclass
class Protocol:
    status_code: str | None
    reason: str | None
    number: str | None
    received_at: datetime | None
    key: str | None


@dataclass
class NFeDocument:
    key: str
    model: str | None
    model_name: str | None
    series: int | None
    number: int | None
    issued_at: datetime | None
    operation: str | None               # entrada | saída
    purpose: str | None                 # normal | complementar | ajuste | devolução
    nature: str | None                  # natOp
    environment: str | None             # production | homologation
    issuer: Party
    recipient: Party | None
    items: list[Item]
    totals: Totals
    freight_mode: str | None
    invoice_number: str | None
    invoice_net: Decimal | None
    installments: list[Installment]
    payments: list[Payment]
    change: Decimal | None              # vTroco
    additional_info: str | None
    fisco_info: str | None
    protocol: Protocol | None
    signed: bool
    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)

    @property
    def authorized(self) -> bool:
        return bool(self.protocol and self.protocol.status_code in AUTHORIZED)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        """JSON-ready: Decimals and dates become strings."""
        return _jsonable(asdict(self)) | {"authorized": self.authorized, "valid": self.valid}


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# --- XML helpers ---------------------------------------------------------------------------

def _load(source) -> ET.Element:
    if isinstance(source, ET.Element):
        return source
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif isinstance(source, str) and source.lstrip().startswith("<"):
        data = source.encode("utf-8")
    elif isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as fh:
            data = fh.read()
    else:
        data = source.read()
        data = data.encode("utf-8") if isinstance(data, str) else data
    # An NF-e never has a DTD. Refusing one closes the door on entity-expansion tricks.
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise InvalidNFeXML("DTDs and entities are not allowed in an NF-e")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise InvalidNFeXML(f"not well-formed XML: {exc}") from None
    for el in root.iter():                 # drop namespaces: {http://...}infNFe -> infNFe
        if isinstance(el.tag, str):
            el.tag = el.tag.rsplit("}", 1)[-1]
    return root


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _dec(el: ET.Element | None, path: str) -> Decimal | None:
    value = _text(el, path)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _flatten(group: ET.Element) -> dict:
    """Leaf tags of a tax group, numbers as Decimal. Nested names stay unique in practice;
    on a clash the later one is stored as parent.tag."""
    out: dict = {}
    for parent in group.iter():
        for child in parent:
            if len(child):
                continue
            text = (child.text or "").strip()
            value: object = text
            if _NUMERIC_TAG.match(child.tag):
                try:
                    value = Decimal(text)
                except InvalidOperation:
                    pass
            key = child.tag if child.tag not in out else f"{parent.tag}.{child.tag}"
            out[key] = value
    return out


def _address(el: ET.Element | None) -> Address | None:
    if el is None:
        return None
    return Address(
        street=_text(el, "xLgr"), number=_text(el, "nro"), complement=_text(el, "xCpl"),
        district=_text(el, "xBairro"), city=_text(el, "xMun"), city_code=_text(el, "cMun"),
        uf=_text(el, "UF"), zip_code=_text(el, "CEP"), country=_text(el, "xPais"),
        phone=_text(el, "fone"),
    )


def _party(el: ET.Element | None, address_tag: str) -> Party | None:
    if el is None:
        return None
    for tag, kind in (("CNPJ", "cnpj"), ("CPF", "cpf"), ("idEstrangeiro", "foreign")):
        doc = _text(el, tag)
        if doc:
            break
    else:
        doc, kind = None, None
    return Party(
        document=doc, document_type=kind, name=_text(el, "xNome"), trade_name=_text(el, "xFant"),
        state_registration=_text(el, "IE"), tax_regime=CRT.get(_text(el, "CRT") or ""),
        email=_text(el, "email"), address=_address(el.find(address_tag)),
    )


def _item(det: ET.Element) -> Item:
    prod = det.find("prod")
    taxes = {}
    imposto = det.find("imposto")
    if imposto is not None:
        for group in imposto:
            taxes[group.tag] = _flatten(group) if len(group) else (group.text or "").strip()
    return Item(
        number=int(det.get("nItem", "0") or 0), code=_text(prod, "cProd"),
        description=_text(prod, "xProd"), ncm=_text(prod, "NCM"), cfop=_text(prod, "CFOP"),
        unit=_text(prod, "uCom"), quantity=_dec(prod, "qCom"), unit_price=_dec(prod, "vUnCom"),
        total=_dec(prod, "vProd"), discount=_dec(prod, "vDesc"),
        ean=None if _text(prod, "cEAN") in (None, "SEM GTIN") else _text(prod, "cEAN"),
        cest=_text(prod, "CEST"), taxes=taxes, additional_info=_text(det, "infAdProd"),
    )


def _totals(total: ET.Element | None) -> Totals:
    icms = total.find("ICMSTot") if total is not None else None
    raw = {}
    if total is not None:
        for group in total:
            raw[group.tag] = _flatten(group)
    return Totals(
        products=_dec(icms, "vProd"), discount=_dec(icms, "vDesc"), freight=_dec(icms, "vFrete"),
        insurance=_dec(icms, "vSeg"), other=_dec(icms, "vOutro"), icms=_dec(icms, "vICMS"),
        icms_st=_dec(icms, "vST"), ipi=_dec(icms, "vIPI"), pis=_dec(icms, "vPIS"),
        cofins=_dec(icms, "vCOFINS"), approximate_taxes=_dec(icms, "vTotTrib"),
        total=_dec(icms, "vNF"), raw=raw,
    )


# --- parse + cross-checks -------------------------------------------------------------------

def parse(source) -> NFeDocument:
    """Parse an NF-e/NFC-e XML: a path, the XML text, bytes, a file object or an Element.

    Accepts the authorized file (`nfeProc`, NF-e + protocol) or the bare `NFe`. Raises
    InvalidNFeXML only when it isn't an NF-e at all; everything else ends up in `errors`.
    """
    root = _load(source)
    if root.tag in ("procEventoNFe", "evento", "envEvento"):
        raise InvalidNFeXML("this is an NF-e event (e.g. cancellation or correction letter), "
                            "not an NF-e")
    inf = root if root.tag == "infNFe" else root.find(".//infNFe")
    if inf is None:
        raise InvalidNFeXML(f"no infNFe element found (root is <{root.tag}>)")

    ide, emit, dest = inf.find("ide"), inf.find("emit"), inf.find("dest")
    key = nfe.clean_key(inf.get("Id", ""))
    cobr, pag, inf_adic = inf.find("cobr"), inf.find("pag"), inf.find("infAdic")
    prot_inf = root.find(".//protNFe/infProt")
    protocol = None if prot_inf is None else Protocol(
        status_code=_text(prot_inf, "cStat"), reason=_text(prot_inf, "xMotivo"),
        number=_text(prot_inf, "nProt"), received_at=_datetime(_text(prot_inf, "dhRecbto")),
        key=_text(prot_inf, "chNFe"),
    )
    model = _text(ide, "mod")
    doc = NFeDocument(
        key=key, model=model, model_name=nfe.MODELS.get(model or ""),
        series=int(_text(ide, "serie") or 0) if _text(ide, "serie") else None,
        number=int(_text(ide, "nNF")) if (_text(ide, "nNF") or "").isdigit() else None,
        issued_at=_datetime(_text(ide, "dhEmi") or _text(ide, "dEmi")),
        operation={"0": "entrada", "1": "saída"}.get(_text(ide, "tpNF") or ""),
        purpose=PURPOSE.get(_text(ide, "finNFe") or ""), nature=_text(ide, "natOp"),
        environment={"1": "production", "2": "homologation"}.get(_text(ide, "tpAmb") or ""),
        issuer=_party(emit, "enderEmit") or Party(None, None, None),
        recipient=_party(dest, "enderDest"),
        items=[_item(det) for det in inf.findall("det")],
        totals=_totals(inf.find("total")),
        freight_mode=FREIGHT.get(_text(inf, "transp/modFrete") or ""),
        invoice_number=_text(cobr, "fat/nFat"), invoice_net=_dec(cobr, "fat/vLiq"),
        installments=[Installment(_text(d, "nDup"), _date(_text(d, "dVenc")), _dec(d, "vDup"))
                      for d in (cobr.findall("dup") if cobr is not None else [])],
        payments=[Payment(_text(p, "tPag"), PAYMENT_METHODS.get(_text(p, "tPag") or ""),
                          _dec(p, "vPag"))
                  for p in (pag.findall("detPag") if pag is not None else [])],
        change=_dec(pag, "vTroco"),
        additional_info=_text(inf_adic, "infCpl"), fisco_info=_text(inf_adic, "infAdFisco"),
        protocol=protocol, signed=root.find(".//Signature") is not None,
    )
    _cross_check(doc, ide, inf.get("versao"))
    return doc


_CENT = Decimal("0.01")


def _cross_check(doc: NFeDocument, ide: ET.Element | None, version: str | None) -> None:
    err, warn = doc.errors.append, doc.warnings.append

    # 1. The access key against the document itself.
    try:
        k = nfe.parse_key(doc.key)
    except nfe.InvalidAccessKey as exc:
        err(Problem("access_key", f"invalid access key in Id: {exc}"))
        k = None
    if k:
        uf_code = _text(ide, "cUF")
        mismatches = [
            name for name, ours, theirs in (
                ("UF", k.key[:2], uf_code), ("model", k.model, doc.model),
                ("series", k.series, doc.series), ("number", k.number, doc.number),
                ("issuer", k.issuer.lstrip("0"), (doc.issuer.document or "").lstrip("0")),
            ) if theirs is not None and ours != theirs
        ]
        if mismatches:
            err(Problem("key_mismatch", "access key disagrees with the document on: "
                        + ", ".join(mismatches)))
        if doc.issued_at and (k.year, k.month) != (doc.issued_at.year, doc.issued_at.month):
            warn(Problem("key_date", "key year/month differs from the issue date"))

    # 2. Documents.
    for role, party in (("issuer", doc.issuer), ("recipient", doc.recipient)):
        if party is None or party.document is None:
            continue
        ok = {"cnpj": is_valid_cnpj, "cpf": is_valid_cpf}.get(party.document_type)
        if ok and not ok(party.document):
            err(Problem("document", f"{role} {party.document_type.upper()} "
                        f"{party.document} is invalid"))

    # 3. Arithmetic: items vs totals, installments vs invoice.
    t = doc.totals
    item_sum = sum((i.total or Decimal(0)) for i in doc.items)
    if t.products is not None and abs(item_sum - t.products) > _CENT:
        err(Problem("totals", f"items add up to {item_sum}, total products says {t.products}"))
    icms_tot = t.raw.get("ICMSTot", {})

    def v(tag):
        return icms_tot.get(tag) if isinstance(icms_tot.get(tag), Decimal) else Decimal(0)

    expected = (v("vProd") - v("vDesc") - v("vICMSDeson") + v("vST") + v("vFCPST") + v("vFrete")
                + v("vSeg") + v("vOutro") + v("vII") + v("vIPI") + v("vIPIDevol"))
    if t.total is not None and abs(expected - t.total) > _CENT and "ISSQNtot" not in t.raw:
        warn(Problem("total_formula", f"vNF is {t.total}, the standard formula gives {expected}"))
    if doc.installments:
        dup_sum = sum((d.amount or Decimal(0)) for d in doc.installments)
        target = doc.invoice_net if doc.invoice_net is not None else t.total
        if target is not None and abs(dup_sum - target) > _CENT:
            warn(Problem("installments", f"installments add up to {dup_sum}, expected {target}"))
    if doc.payments and t.total is not None:
        paid = sum((p.amount or Decimal(0)) for p in doc.payments) - (doc.change or Decimal(0))
        if paid and abs(paid - t.total) > _CENT and not any(p.method_code == "90"
                                                            for p in doc.payments):
            warn(Problem("payments", f"payments minus change are {paid}, total is {t.total}"))

    # 4. Authorization.
    if doc.protocol is None:
        warn(Problem("no_protocol", "no authorization protocol (protNFe): this is the file "
                     "before SEFAZ authorization, or only part of it"))
    else:
        if doc.protocol.status_code not in AUTHORIZED:
            err(Problem("not_authorized", f"SEFAZ status {doc.protocol.status_code}: "
                        f"{doc.protocol.reason}"))
        if doc.protocol.key and nfe.clean_key(doc.protocol.key) != doc.key:
            err(Problem("protocol_key", "the protocol belongs to another access key"))
    if doc.environment == "homologation":
        warn(Problem("homologation", "issued in the test environment: no fiscal value"))
    if not doc.signed:
        warn(Problem("unsigned", "no XML signature found"))
    if version and version != "4.00":
        warn(Problem("version", f"layout version {version}; this reader targets 4.00"))
