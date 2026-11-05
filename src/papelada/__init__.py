"""papelada: Brazilian financial and fiscal paperwork, read and checked by code.

Boletos and utility slips, NF-e XML, CPF/CNPJ (alphanumeric included), NF-e keys and Pix.
"""
from . import arrecadacao, boleto, documentos, nfe, nfe_xml, pix
from ._inspect import Problem, SlipInfo, find_slips, inspect
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
    "arrecadacao", "boleto", "documentos", "nfe", "nfe_xml", "pix",
    "Boleto", "InvalidBoleto", "parse_slip", "inspect", "find_slips", "SlipInfo", "Problem",
    "is_valid_cpf", "is_valid_cnpj", "is_alphanumeric_cnpj", "format_cpf", "format_cnpj",
]
__version__ = "0.3.0"
