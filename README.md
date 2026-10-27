# boleto-br

**Brazilian payment and fiscal identifiers, done right.** Bank slips (boletos) with the **February 2025
due-date reset**, utility and tax slips, CPF and CNPJ (including the **alphanumeric CNPJ** of 2026),
NF-e access keys, and **Pix "copia e cola"** codes. Pure Python, zero dependencies, fully typed.

```bash
pip install git+https://github.com/hassan-hamdan99/boleto-br
```

> Written from the public specifications (FEBRABAN, Receita Federal, SEFAZ layouts and the Central Bank's
> BR Code manual) and checked against their published reference values.

## Why

These checks sit in front of every accounts-payable automation in Brazil, and they are easy to get subtly
wrong:

- **The due-date factor wrapped around.** It hit 9999 on 2025-02-21 and restarted at 1000 the next day,
  so `1000` now means 2025-02-22, not 2000-07-03. Code that still adds the factor to 1997-10-07 puts new
  slips 25 years in the past.
- **CNPJs are no longer numeric.** Since July 2026, new CNPJs can contain letters (`12.ABC.345/01DE-35`).
  Validators that strip non-digits silently reject them.
- **OCR and LLM extraction need a deterministic referee.** When a model reads a boleto from a PDF, the
  check digits are what tells you whether it read it right.

## Usage

```python
from datetime import date
from boleto_br import boleto, arrecadacao, nfe, pix, parse_slip, is_valid_cnpj

slip = boleto.parse("34191.09008 61207.727308 71140.050007 4 16460000125000")  # line or barcode
slip.bank_name, slip.amount, slip.due_date
# ('Itaú Unibanco', Decimal('1250'), datetime.date(2026, 11, 30))
slip.barcode   # '34194164600001250001090061207727307114005000'

bill = parse_slip("83620000001-3 87430001000-4 00000000000-0 00012345678-2")  # starts with 8: arrecadação
bill.segment_name, bill.amount   # ('Energia elétrica e gás', Decimal('187.43'))

boleto.due_date(1000)                      # date(2025, 2, 22): the cycle closest to today
boleto.due_date_factor(date(2026, 1, 1))   # 1313

is_valid_cnpj("12.ABC.345/01DE-35")    # True: alphanumeric CNPJ

key = nfe.parse_key("4226 1011 2223 3300 0181 5500 1000 0123 4511 2345 6789")
key.uf, key.model_name, key.number     # ('SC', 'NF-e', 12345)

payload = pix.build("pix@example.com", "Loja Exemplo", "FLORIANOPOLIS", amount=49.90, txid="PEDIDO123")
pix.parse(payload).amount      # Decimal('49.90'); the CRC16 is checked on parse
```

## What's covered

| Module | Validates | Extracts / builds |
|---|---|---|
| `boleto` | Field check digits (módulo 10) and general check digit (módulo 11) | Bank, amount, due date, free field · line ↔ barcode · `build()` for synthetic slips |
| `arrecadacao` | Módulo 10 or 11 depending on the value type, per block and general | Segment, amount, company id · line ↔ barcode |
| `documentos` | CPF; CNPJ numeric **and alphanumeric** | Formatting |
| `nfe` | 44-digit access key (módulo 11), UF code, month, issuer CNPJ/CPF | UF, year/month, model (NF-e, NFC-e, CT-e, MDF-e), series, number |
| `pix` | CRC16-CCITT-FALSE, TLV structure, Pix GUI, currency | Key and key type (CPF, CNPJ, e-mail, phone, random), amount, merchant, txid · `build()` static codes |

## Verified against

| Reference | Result |
|---|---|
| Receita Federal's alphanumeric CNPJ example `12.ABC.345/01DE-35` | check digits `35` ✔ |
| Central Bank BR Code manual example (`…63041D3D`) | parsed, and **rebuilt byte for byte** ✔ |
| CRC16-CCITT-FALSE check value of `"123456789"` | `29B1` ✔ |
| Factor 1000 → 2000-07-03, 9999 → 2025-02-21, reset → 2025-02-22 | ✔ |

Plus **46 tests**: thousands of randomized round-trips (line → barcode → line), single-digit typo detection
on every position, and validation of generated CPFs and CNPJs.

### A note on what check digits can't catch

FEBRABAN maps general check digits 0, 10 and 11 to `1`. A few single-digit errors in the amount or due
date are therefore **undetectable by design**. Measured over 28,000 typos, the general digit catches
**98.3%** of them. The tests assert the spec, not a stronger guarantee the format doesn't give. If a wrong
amount is costly, cross-check it against another source (the invoice, the PDF text).

## Development

```bash
pip install -e ".[dev]"
pytest --cov=boleto_br
```

MIT License
