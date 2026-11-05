# papelada

**Brazilian financial and fiscal paperwork, read and checked by code.** Boletos and utility slips,
NF-e / NFC-e XML, CPF and CNPJ (including the **alphanumeric CNPJ** of 2026), NF-e access keys and
**Pix "copia e cola"** codes. Pure Python, zero dependencies, fully typed.

[![PyPI](https://img.shields.io/pypi/v/papelada?color=34d399)](https://pypi.org/project/papelada/)
[![Python](https://img.shields.io/pypi/pyversions/papelada)](https://pypi.org/project/papelada/)
[![tests](https://github.com/hassan-hamdan99/papelada/actions/workflows/tests.yml/badge.svg)](https://github.com/hassan-hamdan99/papelada/actions/workflows/tests.yml)

```bash
pip install papelada
```

> Written from the public specifications (FEBRABAN, Receita Federal, the NF-e taxpayer manual and
> technical notes, the Central Bank's BR Code manual) and checked against their published reference values.

## Why

Every finance automation in Brazil starts by reading this paperwork, and it is easy to get subtly wrong:

- **The due-date factor wrapped around.** It hit 9999 on 2025-02-21 and restarted at 1000 the next day,
  so `1000` now means 2025-02-22, not 2000-07-03. Code that still adds the factor to 1997-10-07 puts new
  slips 25 years in the past.
- **CNPJs are no longer numeric.** Since July 2026, new CNPJs (and the NF-e access keys that carry
  them) can contain letters: `12.ABC.345/01DE-35`. Validators that strip non-digits silently reject them.
- **OCR and LLM extraction need a deterministic referee.** When a model reads a boleto from a PDF, the
  check digits are what tells you whether it read it right, and an NF-e's own totals tell you whether
  the numbers add up.

The design rule throughout: **report, don't guess.** Readers return every problem they find, with
positions and machine-readable codes, and never "fix" anything silently.

## Slips: `inspect()`

One call, any code: 47-digit bank slip line, 48-digit utility/tax line or 44-digit barcode, formatted
or not. It never raises. It tells you what the code is, what's wrong with it and what it says.

```python
from papelada import inspect

info = inspect("34191.09008 61207.727308 71140.050007 4 16460000125000")
info.kind, info.valid, info.bank_name           # ('boleto', True, 'Itaú Unibanco')
info.amount, info.due_date, info.due_status     # (Decimal('1250.00'), date(2026, 11, 30), 'upcoming')
info.to_dict()                                  # JSON-ready, for APIs, n8n and LLM tools

bad = inspect("34191.09009 61207.727308 71140.050007 4 16460000125000")   # one wrong digit
bad.valid, bad.errors[0].message   # (False, 'wrong check digit in field 1')
bad.suggestions                    # ['34191090086120772730871140050007416460000125000']

bill = inspect("83620000001-3 87430001000-4 00000000000-0 00012345678-2")
bill.kind, bill.segment_name, bill.amount   # ('arrecadacao', 'Energia elétrica e gás', Decimal('187.43'))
```

**Suggestions are for OCR and LLM extraction.** When a code is invalid, `inspect()` lists the valid
codes one edit away (a wrong, missing, extra or swapped digit). Over 1,000 simulated typos the right
code was always among them, but how many there are depends on where the typo is:

| Typo in | Exactly one candidate | Right code in the list |
|---|---|---|
| Fields 1-3 (own check digit) | 32% | 100%, usually 1 to 4 candidates |
| Due date / amount (field 5) | 2% | 100%, but 10+ candidates |

So it never auto-corrects. With one candidate you can confirm it with the user; with up to five, let
them pick; with more, it returns none (never a truncated list that might miss the right one) and
warns `ambiguous_fix`, which means: ask for the code again.

**Find slips in free text** (an e-mail, PDF text, a WhatsApp message), including lines broken across
two lines. The same slip given as line and barcode comes back once:

```python
from papelada import find_slips
for slip in find_slips(email_body):
    print(slip.kind, slip.amount, slip.due_date)
```

### A note on what check digits can't catch

FEBRABAN maps general check digits 0, 10 and 11 to `1`. A few single-digit errors in the amount or due
date are therefore **undetectable by design**. Measured over 28,000 typos, the general digit catches
**98.3%** of them. The tests assert the spec, not a stronger guarantee the format doesn't give. If a wrong
amount is costly, cross-check it against another source, such as the NF-e below.

## NF-e and NFC-e XML: `nfe_xml.parse()`

Reads the authorized file (`nfeProc`) or the bare `NFe`, layout 4.00, from a path, text, bytes or file.

```python
from papelada import nfe_xml

doc = nfe_xml.parse("nota.xml")
doc.issuer.name, doc.recipient.document, doc.totals.total
doc.items[0].description, doc.items[0].ncm, doc.items[0].cfop, doc.items[0].taxes["ICMS"]
doc.installments    # [Installment(number='001', due_date=date(2026, 11, 15), amount=Decimal('50.00')), ...]
doc.payments        # [Payment(method_code='15', method='Boleto bancário', amount=Decimal('100.00'))]
doc.authorized, doc.valid, doc.errors, doc.warnings
doc.to_dict()
```

**What it reads:** identification (model, series, number, issue date, operation, purpose, environment),
issuer and recipient with address and tax regime, every item with every tax group, all totals,
freight mode, invoice and installments (*duplicatas*), payments and change, additional information and
the SEFAZ authorization protocol.

**Tax groups are read generically**, so groups the reader has never seen come through as they are:
the IBS/CBS groups of the tax reform show up in `item.taxes["IBSCBS"]` and `totals.raw` without any
special code.

**What it checks**, reported in `errors` (the document contradicts itself or isn't authorized) and
`warnings` (worth a look):

- the access key's check digit, and that the key agrees with the document on UF, model, series,
  number and issuer (alphanumeric CNPJ included);
- issuer and recipient CPF/CNPJ;
- items add up to the products total, and `vNF` matches the standard formula;
- installments add up to the invoice, and payments minus change add up to the total;
- the protocol says authorized (status 100 or 150) and belongs to this key;
- test environment (no fiscal value), missing signature, unexpected layout version.

**Safe to feed untrusted files:** documents with a DTD or entity declarations are refused (an NF-e
never has one), which closes the door on entity-expansion attacks. It does **not** verify the XML-DSig
signature or query SEFAZ: for that, use the official consultation service.

## Documents, keys and Pix

```python
from datetime import date
from papelada import boleto, nfe, pix, is_valid_cnpj

boleto.due_date(1000)                      # date(2025, 2, 22): the cycle closest to today
boleto.due_date_factor(date(2026, 1, 1))   # 1313

is_valid_cnpj("12.ABC.345/01DE-35")    # True: alphanumeric CNPJ

key = nfe.parse_key("4226 1011 2223 3300 0181 5500 1000 0123 4511 2345 6789")
key.uf, key.model_name, key.number     # ('SC', 'NF-e', 12345)

payload = pix.build("pix@example.com", "Loja Exemplo", "FLORIANOPOLIS", amount=49.90, txid="PEDIDO123")
pix.parse(payload).amount      # Decimal('49.90'); the CRC16 is checked on parse
```

| Module | Validates | Extracts / builds |
|---|---|---|
| `inspect`, `find_slips` | Everything below, without raising | Kind, fields, due status, problems with positions, typo suggestions |
| `boleto` | Field check digits (módulo 10) and general check digit (módulo 11) | Bank, amount, due date, free field · line ↔ barcode · `build()` |
| `arrecadacao` | Módulo 10 or 11 depending on the value type, per block and general | Segment, amount, company id · line ↔ barcode |
| `nfe_xml` | Key, documents, arithmetic, protocol | Parties, items, taxes, totals, installments, payments |
| `nfe` | 44-character access key (módulo 11, alphanumeric issuer), UF, month, issuer | UF, year/month, model (NF-e, NFC-e, CT-e, MDF-e), series, number |
| `documentos` | CPF; CNPJ numeric **and alphanumeric** | Formatting |
| `pix` | CRC16-CCITT-FALSE, TLV structure, Pix GUI, currency | Key and key type, amount, merchant, txid · `build()` static codes |

## Command line

```bash
papelada 34191.09008 61207.727308 71140.050007 4 16460000125000   # inspect a slip code
papelada nota.xml                                                 # read an NF-e / NFC-e
pdftotext fatura.pdf - | papelada                                 # find every slip in a PDF
```

JSON out; exit code 0 when valid, 1 otherwise. Handy from n8n's Execute Command node or a shell script.

## Verified against

| Reference | Result |
|---|---|
| Receita Federal's alphanumeric CNPJ example `12.ABC.345/01DE-35` | check digits `35` ✔ |
| NT Conjunta 2025.001: access key pattern `\d{6}[A-Z0-9]{12}\d{26}`, check digit with ASCII − 48 | ✔ |
| Central Bank BR Code manual example (`…63041D3D`) | parsed, and **rebuilt byte for byte** ✔ |
| CRC16-CCITT-FALSE check value of `"123456789"` | `29B1` ✔ |
| Factor 1000 → 2000-07-03, 9999 → 2025-02-21, reset → 2025-02-22 | ✔ |

Plus **71 tests**: thousands of randomized round-trips, single-digit typo detection on every position,
synthetic NF-e documents with every kind of contradiction, and a refused entity bomb. All test data is
synthetic.

## Roadmap

- [ ] **CNAB 240 / 400**: read return files (`.ret`) and write remittance files (`.rem`), from the
  public FEBRABAN layouts, with the same "report, don't guess" validation.
- [ ] **Slip ↔ NF-e reconciliation**: match boletos to the installments (*duplicatas*) of an invoice by
  amount, due date and issuer, and explain every mismatch.
- [ ] **OFX** bank statements.

## Development

```bash
pip install -e ".[dev]"
pytest --cov=papelada
```

MIT License
