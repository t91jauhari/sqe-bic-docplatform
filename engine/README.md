# Application, LLD, Underlying Invoice, Valas 1/2 and eKTP extraction test

The application uses Spider-AI. This folder also retains a separate legacy CLI; its sample filenames below are placeholders. Customer PDFs are not distributed in the public source export. Supply your own files explicitly.
Drop this folder into `tools/sinarmas_extraction_test/` in your project. It is a standalone Python 3.10+ CLI; it does not require changes to your FastAPI app. Example placeholder filenames are `samples/customer_transaction.pdf`, `samples/customer_lld.pdf`, and `samples/customer_invoice.pdf`.

The implementation pins `llama-cloud==2.16.0` and uses v2 Parse/Extract APIs. It uploads once, explicitly configures Parse for Indonesian + English OCR, forms enrichment and layout, then passes the **completed Parse job ID** as Extract's `file_input`. Extract supports this input and reuses the Parse result. It does not feed Markdown into Extract or parse the PDF twice.

## Process all sample PDFs

Keep your PDFs directly inside `samples/`, with filenames ending in `_lld.pdf`, `_transaction.pdf` or `_invoice.pdf`, plus `_valas2.pdf` and `_valas1.pdf` for the declarations, and `_ektp.pdf` for eKTP. Add as many named samples as needed, such as `customer_lld.pdf`, `customer_transaction.pdf`, or `Forex - Customer_invoice.pdf`.

From this folder, using your working `.env`:

```powershell
.\run_batch.bat --env-file .env
```

Equivalent installed-environment command: `python run.py --batch --env-file .env`. On Linux/WSL: `bash run_batch.sh --env-file .env`. Parse and Extract both default to `agentic_plus`.

| Filename suffix | Automatically selected profile | Individual CSV |
|---|---|---|
| `_lld.pdf` | LLD schema, prompts and policy | 36 requested columns |
| `_transaction.pdf` | Application schema, prompts and policy | 23 requested columns |
| `_invoice.pdf` | Underlying Invoice schema, prompts and policy | 19 requested columns |
| `_valas2.pdf` | Surat Pernyataan Pembelian Valas 2 schema, prompts and policy | 10 requested columns |
| `_valas1.pdf` | Surat Pernyataan Pembelian Valas 1 schema, prompts and policy | 16 requested columns |
| `_ektp.pdf` | eKTP schema, prompts and policy | 20 requested columns |

Matching is case-insensitive. Only files directly in the selected directory are processed; subdirectories are not traversed. Unrelated or incorrectly named files such as `invoice.pdf` or a legacy `customer.pdf` are ignored and listed in the batch summary. The document type comes from the suffix; batch mode processes all six types automatically.

If your input directory is named `sample` instead of `samples`, or is elsewhere:

```powershell
.\run_batch.bat --env-file .env --samples-dir "C:\tjauhari\llama-space\sample"
```

Each batch creates `outputs/batch_<UTC timestamp>/`. Every matched PDF gets a separate folder based on its filename, for example:

| Output path within the batch folder | Contents |
|---|---|
| `documents/0001_customer_invoice/result.csv` | Underlying Invoice values, 19 columns |
| `documents/0002_customer_lld/result.csv` | Customer LLD values, 36 columns |
| `documents/0003_customer_transaction/result.csv` | Customer Application values, 23 columns |
| Each document folder's `raw.csv`, `validation.json`, metadata and `state.json` | Original evidence, rules, cloud responses and job IDs |
| `application_result.csv` | All Application PDFs, one row per file; 8 metadata + 23 Application fields |
| `lld_result.csv` | All LLD PDFs, one row per file; 8 metadata + 36 LLD fields |
| `invoice_result.csv` | All Underlying Invoice PDFs, one row per file; 8 metadata + 19 Invoice fields |
| `valas_declaration_2_result.csv` | All Valas 2 declarations, one row per file; 8 metadata + 10 declaration fields |
| `valas_declaration_1_result.csv` | All Valas 1 declarations, one row per file; 8 metadata + 16 declaration fields |
| `ektp_result.csv` | All eKTP cards, one row per file; 8 metadata + 20 card fields |
| `<document_type>_columns.json` | Mapping from that summary CSV's field names to original display headers |
| `summary.json` | Processing/validation counts, ignored files and each document's output folder |

The numeric folder prefix follows the alphabetical processing order and avoids filename collisions. Filenames and identifiers remain attached to the result throughout processing. Keep your existing `.env` when updating this package; it is never included in the ZIP.

### Summary CSVs grouped by document type

Each document type present in the batch gets its own summary: `application_result.csv` (**31 columns**), `lld_result.csv` (**44 columns**), `invoice_result.csv` (**27 columns**), `valas_declaration_2_result.csv` (**18 columns**), `valas_declaration_1_result.csv` (**24 columns**) or `ektp_result.csv` (**28 columns**). No mixed-type combined CSV is produced. Types with no matching PDFs do not get an empty summary CSV.

Every summary starts with the same 8 metadata columns: `source_file`, `document_type`, `processing_status`, `validation_status`, `output_directory`, `error`, `failed_fields` and `review_fields`. Failed/review field names are separated by semicolons. The remaining columns are only that profile's unique internal field keys, in schema order, such as `branch`, `transaction_id` or `invoice_number`. Each `<document_type>_columns.json` maps these keys to their original display headers.

The individual document CSVs retain the exact original display headers and ordering, including duplicate headers. Grouped summary cells reuse the individual exported cells so decimal formatting, leading zeros, text and structured evidence are retained exactly. Invoice line items are aligned JSON arrays inside their four cells; `line_items.csv` provides a flat audit table for that PDF. `summary.json` includes overall and per-type counts and paths to the grouped CSVs.

One PDF produces one row, even if processing fails. `processing_status=COMPLETED` means its extraction and exports succeeded; `validation_status` can still be PASS, FAIL or REVIEW. A cloud/file/schema failure becomes `processing_status=ERROR`, with empty extracted cells and an `error.json` in that document folder. The runner continues to later PDFs. An error cannot produce extracted per-document `result.csv` data; successful documents, including those with validation FAIL/REVIEW, do produce it.

The grouped CSVs and summary are saved before processing starts and after every document, using temporary-file replacement. Ctrl+C marks the active document INTERRUPTED and leaves later rows PENDING while keeping completed results. SDK response bodies and API keys are not written into batch error messages. Failed billable creations are not automatically retried. Inspect the document's saved state/job IDs before resubmitting after a timeout or interruption.

Exit code 0 means the batch completed without processing errors, even if documents need review or fail business validation. Code 1 means at least one processing error (or invalid batch setup); code 130 means an interrupted batch. Each run uses a fresh directory. If specifying `--output`, choose a new or empty directory so prior results cannot be overwritten.

### Batch settings

Shared settings such as `--parse-tier`, `--extract-tier`, versions, timeout, reference date, `.env` and approved name directory are forwarded to each document. Policies remain separate:

```powershell
.\run_batch.bat --env-file .env --application-policy "C:\config\application-policy.json" --lld-policy "C:\config\lld-policy.json" --invoice-policy "C:\config\invoice-policy.json" --validation-context "C:\data\lld-history.json" --invoice-validation-context "C:\data\invoice-history.json"
```

These options are optional; defaults use `policy.json`, `lld/policy.json`, `invoice/policy.json`, `valas2/policy.json`, `valas1/policy.json` and `ektp/policy.json`. In batch mode, `--validation-context` is forwarded to LLD documents, `--invoice-validation-context` to Invoice documents, `--valas2-validation-context` to Valas 2 declarations, `--valas1-validation-context` to Valas 1 declarations, and `--ektp-validation-context` to eKTP cards. Use `--valas2-policy` or `--valas1-policy` for their batch policy overrides; eKTP uses `--ektp-policy`. History snapshots are not database updates. Repeated invoice numbers among completed PDFs in the current batch mark **all copies** as FAIL in their validation reports and grouped summary rows, without additional cloud jobs. The single-file `--policy` option is not accepted in batch mode.

Inspect filename routing and schemas without uploading or needing a key:

```bash
python run.py --batch --dry-run
```

Dry runs populate the grouped CSVs with DRY_RUN statuses and no extracted values; their document folders contain schema/config snapshots. The original single-file commands, replay and resume remain available.

## eKTP identity card

The eKTP profile has exactly twenty fields. Add your card PDF with an `_ektp.pdf` suffix; no actual eKTP PDF was supplied with this change.

```powershell
.\run_ektp.bat --env-file .env --pdf .\samples\customer_ektp.pdf
```

It preserves NIK digits, normalizes RT/RW to three digits, validates the supplied text/enums/date rules and records signature/photo evidence. Signature-reference matching requires a trusted comparison result; the inaccessible linked stamp requirement number 6 defaults to REVIEW until configured. See [eKTP setup and rules](ektp/README.md) for the complete field mapping, dated-validity rule, comparison context and synthetic replay example. Batch results go to a separate `ektp_result.csv`.

## Valas 1 above-threshold purchase declaration

The new **Surat Pernyataan Pembelian Valas 1 (Diatas Jumlah Threshold)** profile has exactly sixteen fields. Add your document with an `_valas1.pdf` suffix; no real declaration PDF was supplied with this change.

```powershell
.\run_valas1.bat --env-file .env --pdf .\samples\customer_valas1.pdf
```

It keeps usage/receipt purposes, dates, amounts and currencies separate; validates NPWP structure and preserves leading zeros; applies the supplied date rules; and shares the signatory/signature/meterai checks with Valas 2. The identity rule supplied as `N` remains configurable and defaults to REVIEW. See [Valas 1 setup and rules](valas1/README.md) for all fields, identity configuration, numeric storage and a synthetic offline replay example. Batch writes `valas_declaration_1_result.csv` separately from every other document type.

## Valas 2 threshold-limited purchase declaration

The new profile is **Surat Pernyataan Pembelian Valas 2 (Paling Banyak Sebesar Jumlah Threshold)**, with exactly ten fields. Add your PDF under `samples/` with a filename ending in `_valas2.pdf`; no real declaration sample was supplied with this change.

```powershell
.\run_valas2.bat --env-file .env --pdf .\samples\customer_valas2.pdf
```

It exports currency only (no amount), normalizes letter dates, validates conditional company signatory name/role/company, meterai denomination/completeness and mandatory handwritten signature evidence. Meterai authenticity requires a trusted external verification result; the separate tenth-column stamp criterion is configurable and defaults to REVIEW because no rule was supplied. See [Valas 2 setup and rules](valas2/README.md) for the exact field mapping, offline replay example and verification context. Batch output remains grouped by document type in `valas_declaration_2_result.csv`.

## Underlying Invoice document

From this folder, using your existing `.env`:

```powershell
.\run_invoice.bat --env-file .env
```

Equivalent: `.\run_sample.bat --document-type invoice --env-file .env`. On Linux/WSL use `bash run_invoice.sh --env-file .env`. Both stages default to `agentic_plus`. An example invoice may be supplied at `samples/customer_invoice.pdf`.

The profile has exactly **19 requested columns**, with all item rows preserved. It checks names/contact data, SWIFT/account formatting, business-day dates, invoice-number uniqueness, quantities/units, printed versus calculated subtotals, totals, tax/fee/discount adjustments and conditional Claim No.2 at 60%. Raw values stay unchanged; printed arithmetic discrepancies or uncertain separators are reported explicitly. See [Invoice setup and rules](invoice/README.md) for financial calculations, number-format configuration and absent fields.

## LLD document

From this folder, using your existing `.env`:

```powershell
.\run_lld.bat --env-file .env
```

Equivalent command: `.\run_sample.bat --document-type lld --env-file .env`. Both Parse and Extract default to `agentic_plus`. On Linux/WSL use `bash run_lld.sh --env-file .env`.

The LLD profile has its own schema, prompts and policy in `lld/`, with **36 output columns**. Your removed column #29, `Value Transaksi`, is omitted; currency and amount remain together inside `Nilai Transaksi`. See [LLD setup and rule mapping](lld/README.md) for its conditional sections, official master configuration, uniqueness checks and stamp criteria. The existing Application profile remains the default when no document type is supplied.

## Test immediately — Windows PowerShell

From this folder:

```powershell
Copy-Item .env.example .env
notepad .env
# Set LLAMA_CLOUD_API_KEY to your real LlamaCloud key, save and close.
.\run_sample.bat
```

The script creates an isolated virtual environment, installs pinned dependencies, and processes `samples/customer_transaction.pdf`. An existing `LLAMA_CLOUD_API_KEY` environment variable overrides `.env` by default; the runner prints its source and warns when the values differ. Use `--env-file .env` to make the file take priority. Set project/organization IDs only if required by your account. For EU or self-hosted deployments, set your correct regional `LLAMA_CLOUD_BASE_URL` as well; jobs/files must belong to the same region and scope.

## Troubleshoot 401 when a direct SDK example works

A working `LlamaCloud(api_key="...")` example confirms that the directly supplied key works for its endpoint and scope. This runner normally loads settings from the environment and `.env` instead; an old environment key, a different base URL, an unwanted scope or a copied `Bearer ` prefix can change the request. The key is never printed or saved.

1. Put the **same working key** in `.env` as `LLAMA_CLOUD_API_KEY=...`, without `Bearer `. Keep optional base URL, project and organization values blank to reproduce the SDK's defaults (unless your working code requires them).
2. Run the read-only authentication check. It lists at most one file without printing its contents, uploading your PDF or creating a processing job:

```powershell
.\run_sample.bat --env-file .env --check-auth
```

3. After it passes, run:

```powershell
.\run_sample.bat --env-file .env
```

The printed API host and key source help compare the two programs. A 401 still means authentication was rejected; a 403 requires checking permissions/scope for the file-list endpoint. Passing the read check does not guarantee permission for every later API operation.

## Linux / WSL

```bash
cd tools/sinarmas_extraction_test
cp .env.example .env
# Edit .env and set LLAMA_CLOUD_API_KEY.
bash run_sample.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py --pdf samples/customer_transaction.pdf
```

For another PDF:

```powershell
.\run_sample.bat --pdf "C:\documents\another-application.pdf"
```

## Results

Every run uses its own `outputs/<UTC timestamp>/` directory. The console prints the directory and each failed/review rule. Important files:

| File | Contents |
|---|---|
| `parse_response.json` | Expanded Parse output, including OCR, forms and layout metadata |
| `parsed.md` | Parsed Markdown, when available |
| `extract_response.json` | Complete expanded extraction response |
| `raw.json` | Original schema-shaped evidence, no normalization |
| `extract_metadata.json` | Original field metadata, citations and confidence |
| `normalized.json` | Values after deterministic normalization, with JSON numbers for money |
| `corrections.json` | Applied aliases, unapplied name suggestions, and per-option checkbox resolutions |
| `validation.json` | All profile fields, raw/normalized values, status, issues and available confidence/citations |
| `result.csv` | Requested columns in order: Application 23, LLD 36, Invoice 19, Valas 2 10, Valas 1 16, eKTP 20; normalized values |
| `raw.csv` | Same profile columns with original evidence |
| `columns.json` | Ordered headers, unique internal keys and cells, preserving duplicate display headers |
| `schema.json`, `request_config.json`, `policy.json` | The exact schema/config/policy used |
| `state.json` | File, Parse and Extract IDs for reuse/resume |

Compound signature/stamp/charge fields are JSON strings inside their CSV cell. The two `A/C no` headers intentionally remain identical, at positions 8 and 10. Use the internal keys in JSON to distinguish them. Import account columns into Excel as **Text** to preserve leading zeros; JSON always retains account identifiers as strings.

Decimal calculations use `Decimal`, and JSON serialization preserves decimals as JSON numbers. CSV cells contain exact decimal text. `raw.json` always retains original numeric punctuation. A successful extraction exits with code 0 even if the document's validation status is FAIL or REVIEW; cloud/file/schema failures exit nonzero.

## Configuration and boundaries

### Context-aware name correction and overlapping checkbox strokes

`schema.py` now asks for per-option visual evidence in the payment, transaction-type and charges sections. Each option has its own `state`, `local_mark_present`, `mark_type`, `tail_overlap_only` and a short `evidence` description. `options_complete` indicates whether every visible option in that section was inspected. Both Parse and Extract prompts distinguish a tick's local short stroke/vertex from its long trailing stroke.

`context.py` reconciles that evidence: an intentional local tick/cross/fill selects its own option; a passing tail without an independent local mark does not. A tick anchored at Debit with a tail crossing Tunai selects Debit, and the reverse layout selects Tunai. The code does not assume a preferred option or chronological pen direction. Two independently marked boxes still fail the one-selection rule. Unlocalized/conflicting marks or incomplete evidence require review. If reconciliation changes the extractor's original `selected` list, the normalized choice is recorded in `corrections.json` and requires review. The raw list is unchanged.

This operates on the service's observations. It is **not an independent computer-vision detector** and cannot guarantee that the model localized a stroke correctly. Benchmark the prompt against labelled checkbox crops/scans, especially faint or crossing marks. When the actual pixels remain ambiguous, use reviewer inspection rather than forcing a choice. Fresh Parse runs are required to use the new Parse instructions; reusing an old Parse job cannot restore visual information that its old output omitted.

`name_directory.json` supplies reviewed canonical names and aliases. The included mapping implements your example:

```json
{"name": "EAST WEST BANK", "aliases": ["EAST WEST PANK"], "bic_prefixes": []}
```

The normalized beneficiary/transaction bank name can become `EAST WEST BANK`; the raw value and original citations remain unchanged. This is a user-specified spelling rule, not a claim that the directory validates a bank's identity. An unknown single-edit spelling such as `EAST WEST BANC` receives a suggestion, not an automatic substitution. Conflicting aliases are left unchanged for review. Verified BIC prefixes, when you explicitly populate them, can block a correction that conflicts with an observed SWIFT. No BIC is invented, and an absent BIC does not prove bank identity.

Use the separate `branch_names` list for the application's local Cabang, and `bank_branch_names` for beneficiary branches. Beneficiary branch entries may include `bank_name` to bind an alias to one canonical parent bank. Both branch lists default to empty so cities/branches are not guessed. Example entries, to replace with your reviewed master data:

```json
{
  "branch_names": [
    {"name": "YOUR CANONICAL BRANCH", "aliases": ["YOUR REVIEWED OCR SPELLING"]}
  ],
  "bank_branch_names": [
    {"name": "YOUR CANONICAL BENEFICIARY BRANCH", "aliases": ["YOUR REVIEWED OCR SPELLING"], "bank_name": "EAST WEST BANK"}
  ]
}
```

Only these name fields receive text corrections. Account identifiers, amounts, dates, person names and signatures are never repaired by this layer. `corrections_require_review=true` is the default. If your approved alias policy allows automatic acceptance, you may set it false; other confidence and validation checks still apply. Edit-distance suggestions are never automatically applied and are not calibrated confidence scores.

Run the enhanced flow (Agentic Plus remains the default for both stages):

```powershell
.\run_sample.bat --env-file .env --parse-tier agentic_plus --extract-tier agentic_plus
```

For another reviewed dictionary, add `--name-directory your-master-data.json`. Replaying old extraction responses still works because the new evidence properties are optional for compatibility; absent local checkbox evidence is explicitly REVIEW. The output still has exactly 23 top-level fields/CSV columns.

If you call the SDK directly with `SCHEMA`, the name correction happens when you call validation, not automatically inside the cloud schema:

```python
from validation import validate
from run import read

report = validate(
    extracted.extract_result,
    extracted.extract_metadata.model_dump(mode="json") if extracted.extract_metadata else {},
    read("policy.json"),
    directory=read("name_directory.json"),
)
print(report["normalized"]["beneficiary_bank"])
print(report["corrections"])
```

Retrieve Extract with `expand=["extract_metadata"]` before this call if your SDK helper does not already expand metadata.

Edit `policy.json`, not the extraction prompt, for business rules:

- Default numeric convention is Indonesian: `150.000` -> `150000`, `100.817,90` -> `100817.90`. For a document using English separators, set `number_locale` to `en_US`. The parser deliberately flags malformed or mixed-locale values such as `3.248.` or `280.80` under `id_ID`; it never repairs them silently. A document that mixes conventions requires review or a reviewed per-field normalization strategy.
- Dates default to day-first. ISO dates and Indonesian/English month names are accepted. Two-digit years use a configured pivot: 00–49 -> 2000–2049; 50–99 -> 1950–1999. Invalid dates, future dates, weekends, Indonesian public holidays, joint leave and configured bank closure dates fail. Holiday data comes from the pinned `holidays` package; verify it against your official bank calendar and add branch closures to `additional_closed_dates`. Use `--as-of 2026-10-05` for repeatable historical tests.
- The currency support list is an editable **test policy**, not a statement of Bank Sinarmas's actual currency support. Currency codes are validated against the installed ISO dataset and your support list. Keep both updated for production.
- Payment/transaction options must have exactly one checked selection. No selection or multiple selections fail; uncertain recognition requires review. Your requested spelling `INKASI` is retained; if your official policy instead uses `INKASO`, edit the enum or add an explicit alias. `debit rekening` -> `Debet Rekening` is the only default alias. No fuzzy correction is applied.
- `Lainnya` requires the Notes field per your stated rule. Its adjacent description is retained separately as `transaction_other_description`; it does not substitute for Notes.
- Beneficiary/remitter names and addresses are required; telephone text is preserved. Account fields permit letters, numbers and hyphens and retain leading zeros. SWIFT is optional, uppercased and structurally checked as an 8/11-character BIC; this does not verify registration or bank ownership. A bank name's completeness cannot be proved by string syntax and is flagged for review when present.
- Amount, exchange rate (mandatory for non-IDR), charges and total must be positive. Missing charges are not invented as zero. Per your positive-charge requirement, an explicit zero charge fails; change that rule if fee-free transfers are valid in your actual policy.
- `amount + charges = total` is checked only when all operands are valid and their currencies are explicitly the same. Different currencies or missing currency labels require review. No FX conversion is invented. You may set `assume_unlabelled_money_currency=true` only when your form contract guarantees unlabelled values share the transaction currency; the default is false.
- Amount-in-words is preserved. A separate expected wording is generated from the total and explicit total currency for supported Indonesian/English wording. Canonical matching ignores punctuation/case. Different wording requires semantic review because valid linguistic variants exist; it is not falsely marked consistent or rejected as a mismatch. Unreadable/partial words fail. Generation never replaces the OCR evidence. Currency-specific grammatical variants beyond the included names require extension before automated approval.
- Signature/stamp fields use nullable booleans: false means visibly absent; null means uncertain. Detection does not authenticate a signature, signatory or stamp.
- **The linked “stamp requirement number 3” was not supplied as a concrete specification.** `bank_stamp_rule_confirmed=false` therefore requires review, even when a stamp is detected. Set it true and configure required stamp text only after confirming your actual rule. If rule 3 requires shape, dimensions, seal matching or other visual criteria, implement that check before enabling automatic acceptance; substring checks alone do not establish those criteria.
- Notes allow ordinary Unicode text/punctuation; unsupported control characters fail. Any narrower symbol whitelist must come from your actual policy. Confidence below 0.90, or unavailable confidence for a present field, requires review. Confidence is the observed service metadata, not a fabricated accuracy estimate. Optional blank fields return NOT_PRESENT.

`schema.py` has all field descriptions and the global prompt. Each of the 23 top-level fields is required by the schema; missing scalar evidence is nullable. Extraction values are locally checked for exact types before validation. You can import `validate(raw, metadata, policy, as_of=None, directory=None)` into your FastAPI service without running the CLI. Pass your reviewed name directory to enable dictionary-based name correction.

## Reuse, resume and offline replay

```bash
# Continue/reuse Parse output, skipping upload and Parse creation:
python run.py --parse-job-id pjb-YOUR-ID

# Resume an existing extraction without creating another cloud job:
python run.py --extract-job-id ext-YOUR-ID

# Reuse uploaded file (starts a new Parse job):
python run.py --file-id dfl-YOUR-ID

# Re-run only local validation/export on a full response (no key/cloud needed):
python run.py --replay outputs/YOUR-RUN/extract_response.json

# Inspect exact schema/config without any network calls:
python run.py --dry-run

# Offline tests, including requests through the actual installed SDK:
python -m unittest discover -s tests -v
```

Default wait limit is 1,200 seconds **per stage**, configurable with `--timeout`. A local timeout does not cancel the remote job; reuse the ID printed in the error or saved in `state.json`. Automatic SDK retries are disabled so a lost creation response does not blindly create another billable job. If creation itself times out before an ID is saved, inspect your LlamaCloud job list before submitting again. Existing jobs expire according to the service's retention policy. Bounding-box sidecar download URLs in Parse metadata may expire; this test preserves the response but does not download sidecars.

Parse and Extract versions default to `latest`, and resolved configuration/responses are saved. Pin `--parse-version` and `--extract-version` to supported dates/version names after benchmarking if reproducibility is required. Agentic Plus is the default for both stages; lower tiers are optional CLI choices.

## Verification performed

163 offline tests passed against installed `llama-cloud==2.16.0`: 25 Application/SDK tests, 20 LLD tests, 26 Invoice tests, 23 Valas 2 tests, 22 Valas 1 tests, 28 eKTP tests and 19 batch tests. Invoice coverage includes the 19-column export, line alignment, main versus packaging quantity, currency/number ambiguity, exact arithmetic comparisons, tax/discount and included-tax handling, conditional progress claims, dates, account/BIC structure and uniqueness. Batch tests verify all six suffixes, matching schemas, individual/grouped export consistency, duplicate invoices, continued processing after errors and interruption checkpoints. A test uses the actual SDK with mocked HTTP responses to verify one upload/Parse/Extract creation per PDF across all six profiles. Valas 2 coverage includes conditional representative fields, currency-only output, multilingual dates, handwritten signature evidence, meterai denomination/cropping, job-matched external authenticity records and separate stamp policy. Valas 1 also covers strict NPWP structures, separately paired usage/receipt data, Indonesian decimal amounts and differing date rules. eKTP coverage includes strict NIK/name/enums, RT/RW padding, multilingual dates, lifetime/dated validity, signature/photo evidence, reference comparison binding and stamp criteria. Test values are synthetic and are not claimed as live extraction results for the included PDFs.

Live cloud extraction has **not** been run: no API key was provided. Run the sample above with your key to measure actual field accuracy and latency. This folder implements extraction and rule reporting; a production banking approval workflow still needs your confirmed bank policy and reviewer decisions.

Official references checked on 2026-10-05:

- [Parse configuration](https://developers.llamaindex.ai/llamaparse/parse/guides/configuring-parse/)
- [Parse create API](https://developers.llamaindex.ai/reference/resources/parsing/methods/create/)
- [Extract configuration](https://developers.llamaindex.ai/llamaparse/extract/guides/configuring-extract/)
- [Extract create API: file or completed Parse job ID](https://developers.llamaindex.ai/reference/resources/extract/methods/create/)
- [Extract response and expanded metadata](https://developers.llamaindex.ai/llamaparse/extract/guides/response-format/)
