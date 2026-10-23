# Surat Pernyataan Pembelian Valas 1 (Diatas Jumlah Threshold)

This profile extracts exactly the **16 supplied columns**, in the supplied order. It separates usage and receipt sections, preserves identity/NPWP digits, parses positive monetary amounts using Indonesian separators, checks the supplied date rules, and shares representative/signature/meterai checks with Valas 2. Schema/prompts, settings and section-specific rules are in `schema.py`, `policy.json` and `validation.py`; common checks are in `../valas_common.py`. Both Parse and Extract default to `agentic_plus`.

## Run your document

No actual Valas 1 PDF was supplied with this change. Put your document directly in `samples/` or your selected `sample` directory with a filename ending in `_valas1.pdf`, for example `customer_valas1.pdf`.

```powershell
.\run_valas1.bat --env-file .env --pdf .\samples\customer_valas1.pdf
```

Linux/WSL:

```bash
bash run_valas1.sh --env-file .env --pdf samples/customer_valas1.pdf
```

Equivalent: `python run.py --document-type valas_declaration_1 --env-file .env --pdf samples/customer_valas1.pdf`. Without an explicit `--pdf`, the profile looks for `samples/customer_valas1.pdf`; this file is not included. File/job reuse, replay and dry run work as for the other profiles.

Process all six supported document types in your directory:

```powershell
.\run_batch.bat --env-file .env --samples-dir "C:\tjauhari\llama-space\sample"
```

Each successful PDF writes its own `result.csv` with 16 fields plus raw evidence, validation, corrections, metadata and job state. Batch groups Valas 1 documents separately into **`valas_declaration_1_result.csv`**, with 8 metadata columns + 16 fields (**24 columns**), one row per Valas 1 PDF. eKTP, Valas 2, Invoice, LLD and Application keep their separate summary CSVs. `valas_declaration_1_columns.json` maps the summary's unique keys to the original headers. A validation FAIL/REVIEW still writes extraction results and allows later PDFs to process.

## Exact fields and supplied rules

| Position | Internal key | Display header | Validation |
|---|---|---|---|
| 1 | `customer_name` | Nama Individu / Perusahaan | Required complete text, preserve case/punctuation, trim spaces, reject symbol-only |
| 2 | `customer_address` | Alamat Individu / Perusahaan | Required complete entered address; incomplete/unreadable text detected |
| 3 | `identity_number` | Nomor Identitas | Preserve leading zeros/format; supplied rule is only `N`, so configured format/requiredness is needed for PASS |
| 4 | `npwp` | Nomor Pokok Wajib Pajak (NPWP) | 15-digit legacy NPWP, formatted or compact, or 16-digit NIK-style format; optional unless explicitly available |
| 5 | `usage_purpose` | Tujuan Penggunaan | Required complete free text; trim spaces, preserve punctuation |
| 6 | `usage_date` | Tanggal Penggunaan | Valid date, DD-MM-YYYY output, business working day and no future date |
| 7 | `usage_amount` | Jumlah Penggunaan | Positive numeric amount using dot thousands/comma decimal, with explicit ISO currency |
| 8 | `receipt_source` | Sumber Penerimaan | Required complete entered receipt/source text |
| 9 | `receipt_date` | Tanggal Penerimaan | Valid complete date; DD-MM-YYYY output; no extra future/weekend restriction supplied |
| 10 | `receipt_amount` | Jumlah Penerimaan | Positive numeric amount using dot thousands/comma decimal, with its own explicit ISO currency |
| 11 | `creation_place` | Kota / Tempat Surat Dibuat | Required place containing letters; numeric/symbol-only input fails |
| 12 | `creation_date` | Tanggal Surat Dibuat | Valid complete date, DD-MM-YYYY output, no future date; weekends allowed |
| 13 | `signatory_signature` | Tanda Tangan Penandatangan | Mandatory visible handwritten signature; typed/font-only or cropped evidence fails |
| 14 | `stamp_duty` | Meterai / Stamp Duty | Actual visible complete meterai, denomination 10000; authenticity needs trusted external verification |
| 15 | `signatory` | Nama dan Jabatan Penandatangan | Separate entered name/role; required for a company representative, optional for clear individual self-signing |
| 16 | `signatory_company` | Nama Perusahaan Penandatangan | Complete entered company name required for representative; optional for clear individual self-signing |

There is no separate currency or company/bank-stamp verification column in this profile. No numeric threshold, threshold comparison, amount equality, currency conversion or ordering relationship between usage and receipt was supplied; the validator does not invent those conditions from the document title.

## Identity number rule

The supplied rule for Nomor Identitas is only `N`. The default policy therefore reports **`IDENTITY_RULE_NOT_CONFIGURED`**, even when a value is extracted. It preserves the entered identifier as text, trims whitespace, detects symbol-only/incomplete values, and does not assume it must be NIK or copy NPWP into it. An unconfigured blank field needs REVIEW rather than an invented mandatory/optional decision.

Once the business rule is confirmed, edit these keys in a copy of the full `policy.json`:

```json
{
  "identity_rule_confirmed": true,
  "identity_required": true,
  "identity_pattern": "[0-9]{16}"
}
```

This is **an example configuration only**, not a statement that every identity number must be 16 digits. Set your actual allowed regex and requiredness. `identity_required=false` allows an absent field; an entered value still needs a configured format. Matching uses the whole trimmed string. Leading zeros remain intact; no digit padding, correction or substitution is applied.

## NPWP

The supplied structural rule accepts:

- Formatted 15-digit NPWP, e.g. `01.234.567.8-901.234`.
- Its compact 15-digit form, e.g. `012345678901234`.
- A 16-digit NIK-style string.

Formatting must be exact; arbitrary dots/dashes, letters, embedded spaces, incorrect digit counts or nonnumeric values fail. The normalized value is a **string** with only the digits; leading zeros remain. Original separators remain in `raw.json` and `raw.csv`. This checks the supplied structure, not tax-registration validity, taxpayer ownership or NIK district/date semantics.

NPWP may be absent. The extractor reports `npwp.available=true/false` only from explicit form evidence, not from a blank field alone. If explicitly available but blank, it fails REQUIRED. Unknown/false availability with a readable blank field is NOT_PRESENT; unknown availability with an unreadable region requires review. An entered NPWP with an explicit no-NPWP statement requires review for conflicting evidence. It is never filled from Nomor Identitas.

## Money, dates and section boundaries

Default `number_locale=id_ID` treats `150.000,50` as numeric `150000.50`, `1.500` as `1500`, and `0,01` as `0.01`. Missing/zero/negative amounts, malformed grouping, scientific notation, and US-formatted `1,500.25` fail. An explicitly approved `en_US` policy override is supported for a different input convention; no automatic locale guessing or correction makes an amount pass.

Each amount retains separate properties, e.g. `{"amount":150000.50,"currency":"USD"}`. **Amount is stored as a JSON number, not a formatted number string.** Currency is kept separately in the same semantic field, maintaining the exact 16-column layout. Its CSV cell is that JSON object. Import identity/NPWP columns into Excel as Text to preserve leading zeros.

Both amounts require their own explicitly associated currency. A shared visible heading may apply to both when unambiguous, but the extractor must not borrow an absent currency from another section, printed threshold wording or Rp10 000 meterai. Explicit ISO codes are normalized to uppercase and checked against the installed currency dataset; reviewed currency-name aliases are configurable. Bare `$`, `¥` or `Dollar` requires review. Usage and receipt currencies may differ; no invented FX conversion is performed.

All three dates normalize independently. Usage date additionally rejects future dates, weekends, configured Indonesian public holidays/joint leave and `additional_closed_dates`. Holiday checks use the pinned installed calendar dataset; configure your bank's additional closure dates in YYYY-MM-DD form. The letter date rejects future dates but allows weekends. Receipt date only receives the supplied valid-date/format checks, including acceptance of valid future/weekend dates. No missing date is copied from another field.

`--as-of YYYY-MM-DD` controls the reference date; otherwise Jakarta today is used. Numeric formats, ISO dates and Indonesian/English month names are supported. Invalid/impossible or incomplete dates fail.

## Signatory and meterai

Company representatives need both an entered signer name and role, plus the explicitly represented company. The extractor cannot invent a title or fill an empty signer-company field from the customer name. Clear individual self-signing may omit the role/company/name block, while the handwritten signature is still mandatory. Unknown capacity requires review; missing role/company alone does not establish individual capacity.

Meterai presence, readable denomination (`Rp10 000` / `Rp10.000` / configured equivalent text), cropping, suspicious features and local signature observations are checked. **OCR alone cannot prove a meterai is genuine.** Until an external verification result is supplied, authenticity remains REVIEW. Matching rejected verification fails; verified status cannot override missing/cropped stamp or typed/missing signature failures.

Use the same trusted record format as [Valas 2](../valas2/README.md#meterai-authenticity), keyed to the actual **Valas 1** `extract_job_id`, with `status`, `verification_reference` and `verified_by`. Records for other jobs are ignored. Keep verification context under the trusted application's control, not generated from model output.

Replay after verification without new billable jobs:

```powershell
python run.py --document-type valas_declaration_1 --replay "C:\outputs\extract_response.json" --policy "C:\config\valas1-policy.json" --validation-context "C:\data\meterai-verifications.json"
```

Batch-specific overrides:

```powershell
.\run_batch.bat --env-file .env --valas1-policy "C:\config\valas1-policy.json" --valas1-validation-context "C:\data\meterai-verifications.json"
```

`--validation-context` is for a single-file declaration; `--valas1-validation-context` is forwarded only to Valas 1 files in batch mode. New extraction IDs become known after processing; supply actual verified records when replaying those responses.

## Try offline immediately

`examples/example_extract_response.json` contains **synthetic test observations**, not real OCR results:

```bash
python run.py --document-type valas_declaration_1 --replay valas1/examples/example_extract_response.json --as-of 2026-10-05
```

It writes the 16-column output and reports REVIEW for the unspecified identity rule and unverified meterai. Schema/config-only inspection:

```bash
python run.py --document-type valas_declaration_1 --dry-run
```

Tests cover all 16 fields, independent amounts/currencies/dates, strict NPWP structure and leading zeros, business-day usage dates, receipt-date rule differences, optional fields, signature/stamp evidence, externally matched authenticity, replay and separate batch summary. No live extraction accuracy is claimed without your actual PDF and API key.
