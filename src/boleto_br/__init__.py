"""Brazilian payment and fiscal identifiers: boletos, utility slips, CPF/CNPJ, NF-e keys and Pix."""
from . import arrecadacao, boleto, documentos, nfe, pix
from .boleto import Boleto, InvalidBoleto
from .documentos import (
    format_cnpj, format_cpf, is_alphanumeric_cnpj, is_valid_cnpj, is_valid_cpf,
)


def parse_slip(code: str):
    """Parse any slip: bank slips (boleto) or utility/tax slips (arrecadação, starts with 8)."""
    from ._digits import only_digits

    d = only_digits(code)
    return arrecadacao.parse(d) if d[:1] == "8" else boleto.parse(d)


__all__ = [
    "arrecadacao", "boleto", "documentos", "nfe", "pix",
    "Boleto", "InvalidBoleto", "parse_slip",
    "is_valid_cpf", "is_valid_cnpj", "is_alphanumeric_cnpj", "format_cpf", "format_cnpj",
]
__version__ = "0.1.0"
