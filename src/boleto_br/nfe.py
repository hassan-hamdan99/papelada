"""Access keys (chave de acesso) of NF-e, NFC-e, CT-e and MDF-e: 44 characters.

Layout: cUF(2) AAMM(4) issuer CNPJ/CPF(14) model(2) series(3) number(9) emission type(1)
random code(8) check digit(1). Check digit: módulo 11, weights 2..9 from the right.
"""
from dataclasses import dataclass

from ._digits import mod11_weighted_sum, only_digits
from .documentos import is_valid_cnpj, is_valid_cpf

UF_CODES = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
MODELS = {"55": "NF-e", "65": "NFC-e", "57": "CT-e", "58": "MDF-e", "67": "CT-e OS"}


class InvalidAccessKey(ValueError):
    pass


def check_digit(first43: str) -> int:
    rest = mod11_weighted_sum(first43) % 11
    return 0 if rest in (0, 1) else 11 - rest


@dataclass(frozen=True)
class AccessKey:
    key: str
    uf: str
    year: int
    month: int
    issuer: str
    issuer_is_valid: bool
    model: str
    model_name: str | None
    series: int
    number: int
    emission_type: str
    random_code: str

    @property
    def formatted(self) -> str:
        return " ".join(self.key[i:i + 4] for i in range(0, 44, 4))


def parse_key(value: str) -> AccessKey:
    k = only_digits(value)
    if len(k) != 44:
        raise InvalidAccessKey("access key must have 44 digits")
    if check_digit(k[:43]) != int(k[43]):
        raise InvalidAccessKey("wrong check digit")
    if k[:2] not in UF_CODES:
        raise InvalidAccessKey(f"unknown UF code: {k[:2]}")
    month = int(k[4:6])
    if not 1 <= month <= 12:
        raise InvalidAccessKey(f"invalid month: {month}")

    issuer = k[6:20]
    # CPF issuers (e.g. rural producers) are stored left-padded with zeros.
    issuer_ok = is_valid_cnpj(issuer) or (issuer.startswith("000") and is_valid_cpf(issuer[3:]))
    return AccessKey(
        key=k, uf=UF_CODES[k[:2]], year=2000 + int(k[2:4]), month=month,
        issuer=issuer, issuer_is_valid=issuer_ok, model=k[20:22], model_name=MODELS.get(k[20:22]),
        series=int(k[22:25]), number=int(k[25:34]), emission_type=k[34], random_code=k[35:43],
    )


def is_valid_key(value: str) -> bool:
    try:
        parse_key(value)
        return True
    except InvalidAccessKey:
        return False
