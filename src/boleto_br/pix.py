"""Pix "copia e cola" codes (BR Code, EMV QR Code merchant-presented format).

The payload is a list of TLV fields: 2-digit id, 2-digit length, value. Field 26 holds the Pix
data (GUI "br.gov.bcb.pix", key or URL), field 62 the transaction id, and field 63 a
CRC16-CCITT-FALSE checksum computed over the whole payload including "6304".
"""
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from .documentos import is_valid_cnpj, is_valid_cpf

GUI = "br.gov.bcb.pix"


class InvalidPix(ValueError):
    pass


def crc16(payload: str) -> str:
    """CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF), 4 uppercase hex digits."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _tlv(data: str) -> dict[str, str]:
    fields, i = {}, 0
    while i < len(data):
        if i + 4 > len(data):
            raise InvalidPix(f"truncated field at position {i}")
        tag, size = data[i:i + 2], data[i + 2:i + 4]
        if not size.isdigit():
            raise InvalidPix(f"invalid length for field {tag}")
        value = data[i + 4:i + 4 + int(size)]
        if len(value) != int(size):
            raise InvalidPix(f"field {tag} is shorter than declared")
        fields[tag] = value
        i += 4 + int(size)
    return fields


def _field(tag: str, value: str) -> str:
    if len(value) > 99:
        raise InvalidPix(f"field {tag} longer than 99 characters")
    return f"{tag}{len(value):02d}{value}"


def key_type(key: str) -> str:
    """Classify a Pix key: cpf, cnpj, email, phone, evp (random key) or unknown."""
    if re.fullmatch(r"\+55\d{10,11}", key):
        return "phone"
    if "@" in key:
        return "email"
    if re.fullmatch(r"\d{11}", key) and is_valid_cpf(key):
        return "cpf"
    if re.fullmatch(r"[0-9A-Z]{12}\d{2}", key) and is_valid_cnpj(key):
        return "cnpj"
    try:
        uuid.UUID(key)
        return "evp"
    except ValueError:
        return "unknown"


@dataclass(frozen=True)
class PixCode:
    payload: str
    key: str | None          # static codes
    url: str | None          # dynamic codes (payload location)
    key_type: str | None
    amount: Decimal | None
    merchant_name: str
    merchant_city: str
    txid: str | None
    description: str | None

    @property
    def is_dynamic(self) -> bool:
        return self.url is not None


def parse(code: str) -> PixCode:
    payload = (code or "").strip()
    if len(payload) < 8 or payload[-8:-4] != "6304":
        raise InvalidPix("missing CRC field (6304)")
    if crc16(payload[:-4]) != payload[-4:].upper():
        raise InvalidPix("CRC mismatch: the code was altered or truncated")

    root = _tlv(payload)
    if root.get("00") != "01":
        raise InvalidPix("payload format indicator must be 01")
    account = _tlv(root.get("26", ""))
    if account.get("00", "").lower() != GUI:
        raise InvalidPix("not a Pix code (missing br.gov.bcb.pix)")
    if root.get("53", "986") != "986":
        raise InvalidPix("currency must be BRL (986)")

    key, url = account.get("01"), account.get("25")
    if not key and not url:
        raise InvalidPix("Pix code has neither a key nor a URL")
    extra = _tlv(root.get("62", ""))
    txid = extra.get("05")
    return PixCode(
        payload=payload,
        key=key,
        url=url,
        key_type=key_type(key) if key else None,
        amount=Decimal(root["54"]) if "54" in root else None,
        merchant_name=root.get("59", ""),
        merchant_city=root.get("60", ""),
        txid=None if txid in (None, "***") else txid,
        description=account.get("02"),
    )


def is_valid(code: str) -> bool:
    try:
        parse(code)
        return True
    except InvalidPix:
        return False


def build(key: str, merchant_name: str, merchant_city: str, amount: Decimal | None = None,
          txid: str = "***", description: str | None = None) -> str:
    """Build a static Pix "copia e cola" code."""
    if not re.fullmatch(r"[A-Za-z0-9]{1,25}|\*\*\*", txid):
        raise InvalidPix("txid must be up to 25 alphanumeric characters (or ***)")
    account = _field("00", GUI) + _field("01", key)
    if description:
        account += _field("02", description)
    body = (
        _field("00", "01")
        + _field("26", account)
        + _field("52", "0000")
        + _field("53", "986")
        + (_field("54", f"{Decimal(amount):.2f}") if amount else "")
        + _field("58", "BR")
        + _field("59", merchant_name[:25])
        + _field("60", merchant_city[:15])
        + _field("62", _field("05", txid))
        + "6304"
    )
    return body + crc16(body)
