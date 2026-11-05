"""Common Brazilian bank codes (COMPE). Public information; not exhaustive."""

BANKS = {
    "001": "Banco do Brasil",
    "004": "Banco do Nordeste",
    "021": "Banestes",
    "033": "Santander",
    "037": "Banpará",
    "041": "Banrisul",
    "047": "Banese",
    "070": "BRB",
    "077": "Banco Inter",
    "085": "Ailos",
    "104": "Caixa Econômica Federal",
    "136": "Unicred",
    "208": "BTG Pactual",
    "212": "Banco Original",
    "237": "Bradesco",
    "260": "Nu Pagamentos",
    "290": "PagSeguro",
    "323": "Mercado Pago",
    "336": "C6 Bank",
    "341": "Itaú Unibanco",
    "380": "PicPay",
    "389": "Banco Mercantil do Brasil",
    "422": "Banco Safra",
    "623": "Banco Pan",
    "633": "Banco Rendimento",
    "655": "Banco Votorantim",
    "707": "Banco Daycoval",
    "741": "Banco Ribeirão Preto",
    "745": "Citibank",
    "748": "Sicredi",
    "756": "Sicoob",
}


def bank_name(code: str) -> str | None:
    return BANKS.get(code)
