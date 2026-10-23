# Surat Pernyataan Pembelian Valas 2 (Paling Banyak Sebesar Jumlah Threshold)

This profile uses the ten requested fields and their supplied rules. Currency means **the currency bought only**; there is no transaction amount field or numeric threshold calculation. Its schema and Parse/Extract prompts are in `schema.py`, rules in `validation.py`, and settings in `policy.json`. Both cloud stages default to `agentic_plus`.

## Run your PDF

Put the declaration directly in `samples/` (or your chosen `sample` folder) with a name ending in `_valas2.pdf`, for example `customer_valas2.pdf`. No actual Valas 2 sample PDF was supplied with this change; add your PDF before running a cloud extraction.

From the package folder:

```powershell
.\run_valas2.bat --env-file .env --pdf .\samples\customer_valas2.pdf
```

On Linux/WSL:

```bash
bash run_valas2.sh --env-file .env --pdf samples/customer_valas2.pdf
```

Equivalent: `python run.py --document-type valas_declaration_2 --env-file .env --pdf samples/customer_valas2.pdf`. Without `--pdf`, this profile looks for `samples/customer_valas2.pdf`; that file is not included. `--file-id`, `--parse-job-id`, `--extract-job-id`, `--replay`, `--policy`, `--as-of` and `--dry-run` work as for the other profiles.

Run every supported document in your directory:

```powershell
.\run_batch.bat --env-file .env --samples-dir "C:\tjauhari\llama-space\sample"
```

Each successful declaration produces its own `result.csv` with ten columns. Batch mode groups all declarations into **`valas_declaration_2_result.csv`**, with 8 metadata columns followed by the ten declaration fields (18 columns total). Other document types keep their separate summary CSVs. Only types present in the batch get a summary. The corresponding `valas_declaration_2_columns.json` maps unique field keys to the display headers below.

## Fields and rules

| Position | Internal key | Display header | Validation |
|---|---|---|---|
| 1 | `customer_name` | Nama (Perusahaan / Individu) | Required text; trim spaces, preserve case/punctuation, reject symbol-only input; inspect completeness |
| 2 | `customer_address` | Alamat (Perusahaan / Individu) | Required full entered address; incomplete/unreadable text fails, uncertain completeness requires review |
| 3 | `currency` | Valuta / Currency | ISO 4217 code only; explicit name aliases may map to a code; ambiguous symbols require review; no amount |
| 4 | `creation_place` | Kota / Tempat Surat Dibuat | Required place containing letters; reject numeric/symbol-only input |
| 5 | `creation_date` | Tanggal Surat Dibuat | Valid complete date, DD-MM-YYYY output, no future dates; weekends are allowed by the supplied rule |
| 6 | `signatory` | Nama dan Jabatan Penandatangan | Separate name and role; both required for representatives; letters, punctuation and spaces; missing/unsupported role detected |
| 7 | `signatory_company` | Nama Perusahaan Penandatangan | Required complete company name for a representative; optional for clearly established individual self-signing |
| 8 | `stamp_duty` | Meterai (Stamp Duty) | Actual visible stamp, complete region, denomination 10000; external authenticity verification required |
| 9 | `signatory_signature` | Tanda Tangan Penandatangan | Mandatory visible handwritten signature and uncropped region; typed/font-only input fails |
| 10 | `stamp_verification` | Stamp verification | Separate company/bank stamp; presence and text requirements configurable; no supplied criterion means REVIEW |

Names and addresses keep their original raw text. Normalized name/address/place/company cells are plain text. `signatory` remains a JSON object with separate name/position/capacity. Meterai, signature and stamp cells retain structured observations, so null/uncertain evidence stays visible. `raw.csv`, `raw.json`, `normalized.json`, `validation.json`, `columns.json` and corrections are also written.

Currency is read from the actual entered/selected purchase-currency field, not from template threshold wording, examples or the Rp10 000 stamp. Codes are normalized to uppercase; reviewed explicit aliases such as `EURO` → `EUR` are configured in `currency_aliases`. Bare `$`, `¥`, or `Dollar` does not automatically become USD/JPY. A value such as `USD 100.000,00` fails the currency-only rule rather than silently removing the amount.

Representative capacity needs visible evidence in `signatory.capacity_evidence`. Blank role/company fields alone do not prove the customer is an individual. A company customer cannot bypass required representative fields by claiming self-signing individual capacity. Clear individual self-signing permits blank signer name/role/company; the handwritten signature is still mandatory. Unknown capacity requires REVIEW. Entered roles without support in the full raw signer text also require REVIEW. The validator does not invent titles or names.

Dates accept day-first numeric formats, ISO dates and Indonesian/English month names. For example, `1/6/1993` becomes `01-06-1993`, and `5 Oktober 2026` becomes `05-10-2026`. The reference date defaults to Jakarta today; use `--as-of YYYY-MM-DD` for a reproducible validation date. This declaration has no business-day/weekend rule.

## Meterai authenticity

OCR checks visible stamp presence, readable denomination and cropping. An empty region or printed placeholder is not an affixed stamp. `Rp10 000`, `Rp10.000`, `10000` and the configured denomination words are supported. Missing/wrong denomination or cropped stamp fails. Visible suspected tampering requires review.

**A scan alone cannot prove whether a meterai is genuine.** The extractor cannot set authenticity to verified. Until your trusted verification/reviewer workflow supplies a result, `stamp_duty` reports `STAMP_DUTY_AUTHENTICITY_REQUIRES_EXTERNAL_VERIFICATION` and REVIEW. This package does not call a stamp issuer or verify security features cryptographically.

To import a real verification result, copy `validation_context.example.json` and add a record tied to the actual extraction job ID from that document's `extract_response.json` or `state.json`:

```json
{
  "stamp_duty_verifications": [
    {
      "extract_job_id": "ext-ACTUAL_DOCUMENT_JOB_ID",
      "status": "verified",
      "verification_reference": "YOUR_REAL_VERIFICATION_REFERENCE",
      "verified_by": "YOUR_VERIFICATION_SERVICE_OR_REVIEWER"
    }
  ]
}
```

Allowed statuses are `verified`, `rejected`, and `unknown`. This is an input for **already completed external verification**, not an instruction to declare a stamp genuine. Keep this context under your trusted application's control; never populate it from model output or document wording. A verified record for another job is ignored. Duplicate matching records require review. A rejected matching record fails. A verified record does not override missing/cropped stamp or signature failures. The record/reference is retained in the audit report.

Replay a completed extraction with that context without new billable jobs:

```powershell
python run.py --document-type valas_declaration_2 --replay "C:\outputs\extract_response.json" --validation-context "C:\data\meterai-verifications.json" --policy "C:\config\valas2-policy.json"
```

Single-file extraction uses `--validation-context`. Batch mode uses `--valas2-validation-context`; its records are matched to each declaration's actual extraction ID. For newly created jobs, verify after extraction and then replay with the verified record.

## Separate stamp verification rule

No criterion was supplied for the tenth column. Default `stamp_rule_confirmed=false` and `stamp_required=null` intentionally require REVIEW without inventing a mandatory company/bank stamp rule. Meterai and handwritten signature rules are enforced independently.

Once your business owner confirms the rule, set, for example:

```json
{
  "stamp_rule_confirmed": true,
  "stamp_required": true,
  "required_stamp_text_fragments": ["YOUR_REQUIRED_COMPANY_OR_BANK_NAME"]
}
```

Edit these keys in a copy of the complete `policy.json`; this snippet alone is not a complete policy. Text matching ignores case and redundant whitespace. Required stamp absent, cropped or missing required text fails. If business rules explicitly allow no stamp, set `stamp_required=false` and `required_stamp_text_fragments=[]` with the rule confirmed; an inspected absent stamp becomes NOT_APPLICABLE. This validates the stated visible criteria, not authenticity of a company rubber stamp.

Batch overrides:

```powershell
.\run_batch.bat --env-file .env --valas2-policy "C:\config\valas2-policy.json" --valas2-validation-context "C:\data\meterai-verifications.json"
```

## Offline example and tests

The included `examples/example_extract_response.json` contains **synthetic test observations**, not OCR results from a real document. To check exports immediately without an API key:

```bash
python run.py --document-type valas_declaration_2 --replay valas2/examples/example_extract_response.json --as-of 2026-10-05
```

It intentionally produces REVIEW for unverified meterai authenticity and the unconfigured separate stamp rule, while still writing all results. Inspect schema/request configuration without any upload:

```bash
python run.py --document-type valas_declaration_2 --dry-run
```

The offline suite checks all ten fields, company versus individual signing, currency-only handling, mixed-language dates, signature failures, stamp cropping/denomination, externally matched verification, confidence, ordered exports and grouped batch routing. Live extraction accuracy cannot be established until your actual declaration PDF and API key are tested.
