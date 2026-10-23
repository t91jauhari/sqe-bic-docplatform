# LLD document profile

This profile uses the same upload -> Agentic Plus Parse -> Agentic Plus Extract -> local validation -> CSV/JSON flow as the Application profile. It reuses the completed Parse job ID for extraction. `lld/schema.py` contains the extraction descriptions and both prompts; `lld/validation.py` applies business rules; `lld/policy.json` controls master data and optional requirements.

## Run immediately

Unzip the package into your project. From `tools/sinarmas_extraction_test/`, use your existing `.env` with the working LlamaCloud key:

```powershell
.\run_lld.bat --env-file .env
```

If this is a new installation, first copy `.env.example` to `.env` and fill in the key. The launcher installs the pinned requirements into `.venv` and processes `samples/customer_lld.pdf`.

To choose another LLD PDF or explicitly set both tiers:

```powershell
.\run_lld.bat --env-file .env --pdf "C:\documents\another-lld.pdf" --parse-tier agentic_plus --extract-tier agentic_plus
```

On Linux/WSL:

```bash
bash run_lld.sh --env-file .env
```

If your environment is already installed:

```bash
python run.py --document-type lld --env-file .env
```

Application remains available through `run_sample.bat`, or `python run.py --document-type application`.

For many LLD, Application, Underlying Invoice and Valas 2 PDFs together, put `*_lld.pdf`, `*_transaction.pdf`, `*_invoice.pdf` and `*_valas2.pdf` files directly in `samples/` and run `.\run_batch.bat --env-file .env`. Each PDF gets its own filename-based output folder and `result.csv`; the batch also produces separate `lld_result.csv`, `application_result.csv` `invoice_result.csv` and `valas_declaration_2_result.csv` summaries for the document types present, with one row per PDF and only that type's fields. See the main [README](../README.md) for the grouped format and batch settings. Use `--samples-dir` if your directory is named `sample` or has another location.

## Exact column mapping

Your original column #29 (`Value Transaksi`) is removed. The remaining **36 columns** stay in the supplied order. Currency is retained as `transaction_value.currency` inside `Nilai Transaksi`, together with the numeric amount. Its normalized CSV cell is, for example, `USD 150000`; JSON retains separate currency and amount properties. There is no extra currency column.

Duplicate display headers remain duplicated in CSV and in the ordered `columns.json` headers. Use the unique keys below when integrating JSON into your application.

| Output column | Original number | Display header | JSON key |
|---|---|---|---|
| 1 | 1 | Tanggal Transaksi / Date of Transaction | `transaction_date` |
| 2 | 2 | Nomor ID Transaksi / ID Number of Transaction | `transaction_id` |
| 3 | 3 | Jenis Rekening / Type of Account | `account_type` |
| 4 | 4 | Nama Penerima Dana | `beneficiary_name` |
| 5 | 5 | Alamat Penerima Dana | `beneficiary_address` |
| 6 | 6 | Kode Pos Penerima Dana | `beneficiary_postal_code` |
| 7 | 7 | No. Telp Penerima Dana | `beneficiary_phone` |
| 8 | 8 | Status Penerima Dana | `beneficiary_status` |
| 9 | 9 | Sandi Negara | `beneficiary_country_code` |
| 10 | 10 | Kategori Penerima Dana | `beneficiary_category` |
| 11 | 11 | Bank | `beneficiary_bank` |
| 12 | 12 | Lembaga/Organisasi Internasional | `beneficiary_international_organization` |
| 13 | 13 | Identitas Penerima | `beneficiary_identity_relation` |
| 14 | 14 | Jenis Identifikasi Penerima | `beneficiary_identification_type` |
| 15 | 15 | Nomor Identifikasi Penerima | `beneficiary_identification_number` |
| 16 | 16 | Nama Pembayar, Pengirim | `payer_name` |
| 17 | 17 | Alamat Pembayar, Pengirim | `payer_address` |
| 18 | 18 | Kode Pos Pembayar, Pengirim | `payer_postal_code` |
| 19 | 19 | No. Telp Pembayar, Pengirim | `payer_phone` |
| 20 | 20 | Status Pembayar, Pengirim | `payer_status` |
| 21 | 21 | Sandi Negara | `payer_country_code` |
| 22 | 22 | Kategori Pembayar, Penerima | `payer_category` |
| 23 | 23 | Bank | `payer_bank` |
| 24 | 24 | Lembaga/Organisasi Internasional | `payer_international_organization` |
| 25 | 25 | Hubungan keuangan antar pelaku transaksi | `financial_relationship` |
| 26 | 26 | Depository correspondent Bank | `depository_correspondent_bank_country_code` |
| 27 | 27 | Jenis Identifikasi Pembayar, Pengirim | `payer_identification_type` |
| 28 | 28 | Nomor Identifikasi Pembayar, Pengirim | `payer_identification_number` |
| 29 | 30 | Nilai Transaksi | `transaction_value` |
| 30 | 31 | Tujuan / Purpose | `purpose` |
| 31 | 32 | Rincian | `details` |
| 32 | 33 | Sandi transaksi | `transaction_code` |
| 33 | 34 | Tanggal | `declaration_date` |
| 34 | 35 | Tanda Tangan nasabah | `customer_signature` |
| 35 | 36 | Pengesahan Bank - tanda tangan petugas | `bank_officer_signature` |
| 36 | 37 | Stamp verification | `bank_stamp` |

The supplied header `Kategori Pembayar, Penerima` is preserved; its field reads the payer category in Part III. The Bank columns read the **category subtype**, not a financial institution's name. Depository correspondent Bank reads its country-code cells as required by your rule.

## Context and corrective behavior

- Both parties have separate names, full continuation addresses, residency, countries, category choices and identification. No value is copied between them or inferred from a country/address association.
- A country is read only beneath the selected residency alternative. A printed `ID` under an unchecked resident box cannot populate a selected nonresident's blank country cells. Country codes accept ISO alpha-2 or alpha-3 and normalize to alpha-2 by default.
- Every checkbox group requests local mark observations for every option, including unchecked options. Selection follows the short tick body/vertex or another intentional local mark. A long tail crossing another option does not select it. Ambiguous/incomplete evidence requires REVIEW; multiple independent selections fail.
- `Penerima dana ≠ Pembayar` and `Penerima dana = Pembayar` remain distinct. When the latter is selected, blank recipient identification fields and blank Part III fields become NOT_APPLICABLE under the form's skip instruction. Existing entries are still validated. The two parties' values are never automatically made identical.
- Category codes map a marked leaf to its parent. C1/C2/C9/C0 belong to Bank; F1/F2 belong to Lembaga/Organisasi Internasional. This keeps the international Bank subtype distinct from the Bank parent category. Bank and international-organization subfields are NOT_APPLICABLE for other parents. Conflicting entries require review.
- Labels can be normalized for case, list prefixes, supported Indonesian/English variants and bilingual separators. Original labels remain in `raw.json`. Codes and labels that disagree fail; unrecognized selections are never guessed.
- Names and addresses retain all readable lines. Partial/unreadable text fails; uncertain completeness requires review. Person/company names receive no spelling substitutions. The Application's approved bank-name directory does not apply to the LLD category enums.
- Transaction and identity numbers remain strings, with leading zeros retained. Whitespace between entered identifier characters can be removed deterministically; formatted NPWP dots/dashes can be removed under the configured policy. Unknown characters are never changed into digits.
- Segmented numeric cells can join observed digits separated by whitespace only when `segmented_cells=true`. Empty leading cells are not invented zeros, and unreadable digits are not reconstructed. Amounts must be positive and use the configured decimal convention. Currency is separately checked against the installed ISO 4217 dataset.
- The transaction date is checked for validity, future dating, weekends, Indonesian holidays/joint leave and configured bank closures. The footer declaration date is checked for validity/future dating only. Both normalize to DD-MM-YYYY. They need not be equal.
- Postal codes are required numeric strings of 1–5 digits. Phones are optional and accept digits, an initial `+`, spaces, parentheses and dashes. Letters and unbalanced parentheses fail. `Rincian` is optional unless `details_required=true`.
- Customer signature, handwritten bank-officer signature and stamp are separate evidence fields. A stamp alone cannot satisfy the officer-signature rule. Detection reports visible evidence; it does not authenticate a signer or seal.

Checkbox processing uses the service's observations. It does not independently inspect pixels, so the offline tests do not establish real scan accuracy. Preserve uncertainty for human review when the visual mark is unclear.

## Official master data and stamp requirements

The requested official account-type, purpose and transaction-code master lists were not supplied. Their policy properties default to `null`:

| Policy property | Accepted configuration | Default behavior |
|---|---|---|
| `account_type_master` | List of string codes, or object mapping code to description | Present value: REVIEW; missing: FAIL |
| `purpose_master` | List of allowed strings, or code-to-description object | Present value: REVIEW; missing: FAIL |
| `transaction_code_master` | List of string codes, or code-to-description object | Present value: REVIEW; missing: FAIL |
| `template_category_master_confirmed` | Boolean after confirming the category/subtype codes | REVIEW until confirmed |
| `stamp_rule_confirmed` | Boolean after implementing/confirming the actual criteria | REVIEW until confirmed |
| `required_stamp_text_fragments` | Required readable text fragments for a confirmed stamp-text rule | Empty list; no invented wording |

Populate `lld/policy.json` with your official bank values. Master entries must be strings to preserve leading zeros. A list checks membership; a code/description object accepts either exact code or exact description (case-insensitive) and normalizes to the canonical code. The example account codes in your request are not treated as an authoritative complete list. The category/subtype mapping supplied in the policy reflects the printed template and remains unconfirmed until you approve it against your bank master.

The recipient Bank rule contains both a master-list requirement and permission to allow invalid/blank input. The default applies these as: blank allowed, unlisted value REVIEW. Configure `beneficiary_bank_allow_blank=false` to require it when the parent is Bank, or `beneficiary_bank_invalid_action="FAIL"` to reject unlisted entries. Payer Bank requires a valid subtype when its parent is Bank. International subtypes require Bank or Non Bank when applicable.

Stamp verification has no supplied acceptance criteria. The default reports absent stamps as FAIL and detected stamps as REVIEW until the rule is configured. Confirmation enables presence, readable/completeness checks and any required text fragments. If your actual criteria require shape, dimensions, seal-template matching or a registry, implement those checks before enabling automatic acceptance; text fragments alone cannot establish them.

`minimum_confidence=0.9` and `require_confidence=true` apply to relevant present fields. Unavailable confidence is REVIEW, never an assumed zero or a fabricated score. Confirm the pinned holiday and ISO datasets against the reference data used by your organization.

## Transaction and identity uniqueness

OCR cannot establish database uniqueness. Without authoritative history, valid identifiers receive REVIEW with `TRANSACTION_UNIQUENESS_NOT_CHECKED` or `IDENTITY_UNIQUENESS_NOT_CHECKED`.

Copy `lld/validation_context.example.json`, populate it from your application, and pass it:

```powershell
.\run_lld.bat --env-file .env --validation-context "C:\data\lld-history.json"
```

Context shape, with synthetic values to demonstrate the format:

```json
{
  "transaction_id_history_complete": true,
  "transaction_ids": ["000001TX"],
  "identity_history_complete": true,
  "identity_records": [
    {"transaction_id": "000001TX", "role": "payer", "value": "001234567890"}
  ]
}
```

Set the completeness flags true only when the lists cover the scope you intend to check. The runner compares transaction IDs across the supplied history. Identity numbers are checked within the transaction and party role (`payer` or `beneficiary`), consistent with uniqueness per transaction. The same customer's identity in another transaction is allowed by default. `identity_number_global_uniqueness=true` changes that scope, if explicitly required by your business policy. These local checks are not an atomic database insertion or concurrency guarantee; enforce the final constraint in your application database.

## Outputs, replay and tests

Every run writes `raw.json`, `normalized.json`, `validation.json`, `result.csv`, `raw.csv`, `columns.json`, corrections and expanded cloud metadata to a new output directory. Normalized name/address fields become plain text; signature/stamp evidence remains structured. Import identifiers/postal codes as Text in spreadsheet applications to preserve leading zeros.

**FAIL or REVIEW still produces the exports.** Exit code 0 means processing/export succeeded; the validation status describes the document. Missing mandatory fields on an incompletely filled form can legitimately fail. No blank transaction ID, postal code or country is fabricated to obtain PASS.

Replay and resume must specify the LLD profile:

```bash
python run.py --document-type lld --replay outputs/YOUR-RUN/extract_response.json
python run.py --document-type lld --parse-job-id pjb-YOUR-LLD-ID --env-file .env
python run.py --document-type lld --extract-job-id ext-YOUR-LLD-ID --env-file .env
python run.py --document-type lld --dry-run
python -m unittest discover -s tests -v
```

Use an LLD response/job with the LLD profile. Reusing an old Parse job preserves its old instructions/output; a fresh Parse run is needed to apply the new LLD Parse prompt.

163 offline tests pass (20 LLD, 25 Application/SDK, 26 Invoice, 23 Valas 2, 22 Valas 1, 28 eKTP, 19 batch). LLD tests use synthetic values, configured synthetic masters and explicitly scoped history. Live extraction has not been run here because no API key was supplied; test with your key to measure the actual scanned form's extraction accuracy.
