# Underlying Invoice profile

This profile uses the existing upload -> Agentic Plus Parse -> Agentic Plus Extract -> validation/export pipeline. Parse's completed job ID is reused for Extract. Field descriptions and both prompts are in `invoice/schema.py`; business rules and calculations are in `invoice/validation.py`; configuration is in `invoice/policy.json`.

## Run immediately

From `tools/sinarmas_extraction_test/`, keeping your working `.env`:

```powershell
.\run_invoice.bat --env-file .env
```

This processes the included `samples/customer_invoice.pdf`. For another invoice:

```powershell
.\run_invoice.bat --env-file .env --pdf "C:\documents\customer_invoice.pdf"
```

Manual installed-environment command: `python run.py --document-type invoice --env-file .env`. Linux/WSL: `bash run_invoice.sh --env-file .env`.

For multiple documents, put files directly in `samples/` and run:

```powershell
.\run_batch.bat --env-file .env
```

Batch suffixes are `_invoice.pdf` (Underlying Invoice), `_lld.pdf` (LLD) `_transaction.pdf` (Application) and `_valas2.pdf` (Valas 2). Every PDF gets a filename-based folder with its own result, and the batch writes separate summary CSVs for each document type present. `invoice_result.csv` contains one row per Invoice PDF, 8 metadata columns and only the 19 Invoice fields using their unprefixed internal keys. Application and LLD results go to `application_result.csv` and `lld_result.csv`. Valas 2 declarations go to `valas_declaration_2_result.csv`. Both Parse and Extract default to `agentic_plus`.

## Exact 19-column mapping

| Column | Display header | Internal key |
|---|---|---|
| 1 | To (Customer Name) | `to_name` |
| 2 | To Address | `to_address` |
| 3 | To Phone | `to_phone` |
| 4 | From (Company Name) | `from_name` |
| 5 | From Address | `from_address` |
| 6 | From Phone | `from_phone` |
| 7 | Bank Name (Payment Note) | `bank_name` |
| 8 | SWIFT Code | `swift_code` |
| 9 | Bank Account Number | `bank_account_number` |
| 10 | Invoice Date | `invoice_date` |
| 11 | Due Date | `due_date` |
| 12 | Invoice Number | `invoice_number` |
| 13 | Item Name | `item_name` |
| 14 | Quantity | `quantity` |
| 15 | Unit Price | `unit_price` |
| 16 | Subtotal | `subtotal` |
| 17 | Subtotal (All Items) | `subtotal_all_items` |
| 18 | Final Total Amount | `final_total_amount` |
| 19 | Claim No.2 (60% of Supply Equipment) Claim Note / Material Arrived at Site | `claim_note` |

`result.csv` always contains these 19 headers in this order and one row for the document. Multiple items are retained as JSON arrays in columns 13–16, using the same row IDs and order. Quantity and unit are separate properties; price has its currency and price denominator. This preserves every item without changing your document-level export layout. `line_items.csv` provides a separate flat table with each item, its quantity/units, price, printed amount, calculated subtotal, difference and check status.

## Extraction and context rules

- Customer, seller, beneficiary company and bank are distinct. A customer destination/port is not automatically a street address; seller telephone is not customer telephone. Missing To Address, To Phone or Due Date stays missing rather than being copied from another section/document.
- Names must contain letters; numeric-only/symbol-only names fail. Addresses permit ordinary Unicode text, digits and punctuation. Redundant whitespace is trimmed and whitespace before commas/semicolons/colons is normalized. Raw punctuation/text is retained. Truncated/unreadable text fails; uncertain completeness requires review.
- Customer phone is required; company phone is optional. Phones allow digits, spaces, dashes, parentheses and one leading international `+`, including `(+62)`. Letters, unsupported symbols, misplaced plus signs and unbalanced parentheses fail.
- Bank name is taken from the payment note, including the visible branch suffix. The shared `name_directory.json` can apply approved aliases with an audit entry; fuzzy matches remain suggestions. Bank master membership is optional by default because your rule says preferably use a master list. Populate `bank_master` and set `bank_master_required=true` if mandatory. No registration/ownership is inferred from a name.
- BIC structure is checked as four alphanumeric prefix characters, two country letters, two alphanumeric suffix characters and an optional three-character branch. Country is checked against the ISO country dataset (plus configured-in-code XK exception). Lowercase input is detected as FAIL even though a normalized uppercase display is retained. Spaces/symbols and invalid lengths fail. This is a structure check, not a Swift-directory registration or bank-ownership check. Reference: [Swift BIC structure](https://www.swift.com/standards/data-standards/bic-business-identifier-code).
- Account identifiers retain leading zeros. Spaces/dashes are removed, and remaining symbols are rejected. Your account rule accepts alphanumeric input but also asks for numeric-only storage: letters are retained and explicitly flagged REVIEW by default. Set `account_storage_mode="numeric_only"` to reject letters, or `"alphanumeric"` after confirming that your official policy accepts them. Letters are never deleted to create a different account number.
- Invoice Date and Due Date normalize to DD-MM-YYYY and must be valid business days, not future dated. Due Date must be on/after Invoice Date. Both use Indonesian holidays/joint leave and configured closures by default. Missing dates fail; no due date is calculated from payment terms. `due_date_allow_future=false` implements your stated requirement; changing it explicitly changes that policy.
- Invoice identifiers allow letters/digits, `-`, `/`, `_`; blank, symbol-only or invalid characters fail. Invoice No, P/O, LOT and customer tax ID are not interchangeable.

## Numeric interpretation

Amount strings are preserved independently of currency. Currency codes are validated against the installed ISO dataset; configured explicit symbols such as `US$` or `HK$` can normalize to USD/HKD. A bare `$` or `¥` requires review rather than assuming a country/currency.

The default `ambiguous_number_action="REVIEW"` considers both supported separator formats. A uniquely interpretable value such as `1,350.00` or `1.350,00` can normalize. A string such as `1,350` or `280.800` has different valid interpretations in the two conventions, so its normalized amount stays null and the report includes both candidates. No separator is changed to make invoice arithmetic agree, and no missing digit is invented.

After verifying the actual conventions, configure explicit field/path overrides in `invoice/policy.json`, for example:

```json
"field_number_locales": {
  "unit_price": "en_US",
  "subtotal": "id_ID"
}
```

This is a configuration-format example, not a claim that those conventions apply to every invoice. A row-specific override can use `"unit_price[1]"`; claim paths include `"claim_note.amount"`, `"claim_note.percentage"` and `"claim_note.base"`. Explicit overrides take precedence. Alternatively, `ambiguous_number_action="USE_CONFIGURED_LOCALE"` enforces the global `number_locale`; use it only after confirming the document contract.

All calculations use Decimal, never binary floating-point. Currency/amount normalization remains auditable through raw values, metadata and `numeric_candidates`. Invalid formats, exponent notation, nonpositive unit prices/subtotals/totals/claims and unreadable numbers fail. Quantity must be a positive integer, with its optional unit preserved separately.

## Arithmetic checks and evidence

The service extracts printed observations only. The local validator calculates:

1. Each line subtotal = main billable quantity × unit price.
2. All-items subtotal = sum of every calculated line subtotal, only when the complete table and aligned rows are available and all currencies agree.
3. Final total = the explicitly identified full-invoice or claim base, plus printed additions and minus deductions.
4. Applicable Claim No.2 amount = 60% of the confirmed eligible equipment base.

Normalized line subtotals, all-items subtotal and final total are **calculated values**; they cannot be replaced by an inconsistent printed value. The printed amounts remain in `raw.json`/`raw.csv`, field reports, `line_items.csv` and `calculations.json`. A mismatch reports FAIL with both values and their difference. A missing printed total still fails its evidence check even if a separate calculated expectation is available. Calculating an expectation does not establish that the amount was actually printed.

Row IDs must be complete, sequential and identical across descriptions, quantities, prices and printed subtotals. Misaligned, duplicated or missing rows fail rather than being silently zipped. An incomplete table prevents a whole-invoice total. Main billing units and price denominator must agree when stated; alternate packaging counts remain notes and never replace the pricing quantity. No weight/packaging conversion is invented.

Known tax, fee, shipping and discount amounts are kept under `final_total_amount.adjustments`, within the existing column. A tax explicitly already included in the base is recorded but not added again. Unknown inclusion, adjustment sign, missing amounts, currency basis or incomplete adjustments prevent a guessed final amount. The implementation does not invent tax rates or derive unprinted taxes from a rate without an explicit, supported base calculation. Verify such documents through review or extend the adjustment calculation if your templates require rate-only taxes.

Rounding defaults to two decimal places, ROUND_HALF_UP, with editable currency overrides. This is a test policy, not a comprehensive currency precision master. `amount_tolerance="0.00"` requires an exact match after the configured rounding; populate a nonzero tolerance only if your official rule permits it. No FX conversion is performed, and values in different currencies are not summed or numerically compared as if they were the same currency.

## Claim No.2 / 60% / material arrived at site

The claim column is conditional. When all pages were inspected and no such note exists, it is NOT_APPLICABLE by default. `claim_required=true` makes absence a failure. Uncertain presence is REVIEW.

When present, preserve the entire visible note, actual claim number, percentage, positive amount and explicit currency. Number/percentage differing from the configured expected `2` / `60` fails. A percentage check requires an explicit eligible basis: either wording that clearly applies the claim to the whole items subtotal, or a separately printed eligible equipment base. Other charges/services are not automatically treated as eligible equipment. Unknown bases require review; the base is never reverse-calculated from the claim.

For claim-only invoices, the final amount can be based on the calculated claim plus applicable adjustments only when the document explicitly identifies that payment basis. The code never picks full-invoice versus claim-only based on which arithmetic result happens to match. A textual milestone is retained as evidence; it does not independently verify that equipment physically arrived at the site.

## Uniqueness and outputs

Without authoritative history, a syntactically valid Invoice Number receives `INVOICE_UNIQUENESS_NOT_CHECKED` REVIEW. Populate the context from your application and pass it for single-file processing:

```powershell
.\run_invoice.bat --env-file .env --validation-context "C:\data\invoice-history.json"
```

For batches use `--invoice-validation-context` so the invoice context stays separate from the LLD context. Example shape with synthetic values:

```json
{
  "invoice_history_complete": true,
  "invoice_numbers": ["INV-2025/001_A", "INV-2025/002_A"]
}
```

Only mark history complete when it covers the intended scope. `invoice_number_case_sensitive=true` is the default. Duplicate invoice numbers in the supplied history fail. Within one batch, all completed copies of a repeated invoice number are marked FAIL in their individual validation reports and grouped summary rows; the runner makes no additional cloud requests to apply this check. Database uniqueness/concurrent insertion remains your application's responsibility.

The usual raw/normalized/CSV/metadata/state files are retained. Invoice-specific outputs are `line_items.csv` and `calculations.json`. FAIL/REVIEW still writes exports and returns exit code 0 when processing succeeded. Missing printed fields, uncertain separators or genuine arithmetic discrepancies are document findings rather than an API processing failure.

Replay and dry run:

```bash
python run.py --document-type invoice --replay outputs/YOUR-RUN/extract_response.json
python run.py --document-type invoice --dry-run
python run.py --batch --dry-run
python -m unittest discover -s tests -v
```

163 offline tests pass: 26 Invoice, 25 Application/SDK, 20 LLD, 23 Valas 2, 22 Valas 1, 28 eKTP and 19 batch tests. The tests are synthetic; SDK requests use mocked responses. Live cloud extraction has not been run here because no API key was provided. Test with your working key to assess actual extraction quality on the supplied document and additional layouts.
