# eKTP: 20 requested fields

The eKTP profile has its own schema, Parse/Extract prompts, policy and validator. Both cloud stages default to `agentic_plus`. Extraction preserves raw printed values; local validation enforces the supplied rules and records permitted normalization. Signature-reference matching and the linked stamp requirement are separate from OCR observations.

## Run your PDF

No real eKTP sample PDF was supplied with this change. Put your card PDF directly in `samples/`, with a filename ending in `_ektp.pdf`, such as `customer_ektp.pdf`.

```powershell
.\run_ektp.bat --env-file .env --pdf .\samples\customer_ektp.pdf
```

Linux/WSL:

```bash
bash run_ektp.sh --env-file .env --pdf samples/customer_ektp.pdf
```

Equivalent: `python run.py --document-type ektp --env-file .env --pdf samples/customer_ektp.pdf`. Without `--pdf`, the profile looks for `samples/customer_ektp.pdf`; it is not included. File/job reuse, offline replay, `--as-of`, policy override and dry run work as for the other profiles.

Mixed batch:

```powershell
.\run_batch.bat --env-file .env --samples-dir "C:\tjauhari\llama-space\sample"
```

Each successfully processed card gets its own **20-column `result.csv`**, raw evidence, validation, corrections, metadata and job state. All eKTP cards in that batch are grouped into **`ektp_result.csv`**, with 8 metadata columns followed by the 20 eKTP fields (**28 columns**). The other five document types keep their separate summary CSVs. `ektp_columns.json` maps unique summary keys to the display headers below. FAIL/REVIEW business validation still produces exports and does not stop later documents.

## Exact columns and supplied rules

| Position | Internal key | Display header | Validation |
|---|---|---|---|
| 1 | `nik` | NIK | Exactly 16 ASCII digits; no spaces, dots, symbols, letters or padding |
| 2 | `name` | Nama | Required complete alphabetic text/spaces; trim whitespace; reject numbers and punctuation |
| 3 | `birth_place` | Tempat Lahir | Required complete letters/spaces only; no digits/punctuation |
| 4 | `birth_date` | Tanggal Lahir | Valid complete date, DD-MM-YYYY output, not future |
| 5 | `gender` | Jenis Kelamin | Exact Laki-Laki or Perempuan, ignoring case |
| 6 | `blood_type` | Golongan Darah | A, B, AB, O or explicit `-`; blank invalid |
| 7 | `address` | Alamat | Full required address, preserving numbers and punctuation |
| 8 | `rt` | RT | 1–3 digits; left-pad to three digits |
| 9 | `rw` | RW | 1–3 digits; left-pad to three digits independently |
| 10 | `village` | Kelurahan/Desa | Complete required free text |
| 11 | `district` | Kecamatan | Complete required free text |
| 12 | `religion` | Agama | Exact supplied enum, case-insensitive; no fuzzy spelling repair |
| 13 | `marital_status` | Status Perkawinan | Belum Kawin, Kawin, Cerai Hidup or Cerai Mati; no abbreviations |
| 14 | `occupation` | Pekerjaan | Complete required free text |
| 15 | `citizenship` | Kewarganegaraan | WNI or WNA |
| 16 | `valid_until` | Berlaku Hingga | SEUMUR HIDUP or valid complete date; dated values must not be future under the supplied rule |
| 17 | `issuance` | Tempat & Tanggal Penerbitan KTP | Separate issuing place/date inside one compound column; place permits letters/spaces/punctuation; date valid and not future |
| 18 | `owner_signature` | Tanda tangan pemilik | Present non-text signature region, complete and uncorrupted; reference mismatch fails, no comparison requires REVIEW |
| 19 | `owner_photo` | Foto Pemilik | Portrait exists, face visible and not cropped; uncertain evidence requires REVIEW |
| 20 | `stamp_verification` | Stamp verification | Linked requirement number 6 must be configured; unavailable criterion defaults to REVIEW |

NIK is always a **string**, preserving leading zeros. Even outer spaces make NIK invalid under the supplied rule. The validator does not repair O/0, remove separators, pad short NIK values, check registration, decode demographic data or derive birth date/gender from the NIK. RT/RW alone are permitted to be zero-padded; raw digits remain in `raw.json`/`raw.csv`, with the padding recorded in `corrections.json`. Import NIK/RT/RW into Excel as Text.

Name and birthplace keep original punctuation in raw evidence but fail if it violates the supplied alphabetic-only rule. Other free-text fields allow numbers/punctuation and detect missing, symbol-only or incomplete values. No fuzzy correction changes a person's name, religion or identifier.

Religion values are in `policy.json`: Islam, Kristen, Katolik, Hindu, **Buddha**, Konghucu, Penghayat Kepercayaan, Kepercayaan Terhadap Tuhan Yang Maha Esa, and the supplied combined slash label. The two full belief descriptions are explicitly accepted. Spelling such as `Budha` and abbreviations such as `... TUHAN YME` fail under this supplied list unless you explicitly approve different policy values. A blood-type `-` passes as explicit unconfirmed blood type, while null/blank does not.

All dates accept numeric, ISO and Indonesian/English month-name formats and normalize independently. A trailing period after a complete year is supported. Impossible/incomplete and future birth/issuance dates fail. `SEUMUR HIDUP` is normalized case-insensitively. **Your supplied non-future requirement is also enforced for dated Berlaku Hingga values**, so a future expiry date fails; no lifetime value is inferred from card age. Weekends are permitted; no business-day rule was supplied for eKTP dates. Default reference date is Jakarta today; use `--as-of YYYY-MM-DD` to reproduce a result.

The single issuance CSV cell contains, for example, `{"place":"Kota Adm. Jakarta Selatan","date":"07-08-2025"}`. Signature, photo and stamp cells remain JSON objects so visible observations and comparison status remain explicit without adding export columns.

## Signature comparison and photo evidence

The extractor checks the holder signature region separately from the issuing official's signature and a printed name. Missing, text-only, cropped/incomplete or corrupted regions fail. Null/unclear observations or missing local evidence require REVIEW.

A visible signature does not prove it matches the owner's trusted reference. The default is **`SIGNATURE_MATCH_REQUIRES_EXTERNAL_COMPARISON`**. This package does not implement a biometric signature-comparison algorithm. A trusted comparison/reviewer workflow can supply a result after comparing this actual card's signature with an approved reference:

```json
{
  "signature_comparisons": [
    {
      "extract_job_id": "ext-ACTUAL_EKTP_EXTRACTION_ID",
      "nik": "ACTUAL_16_DIGIT_NIK",
      "status": "matched",
      "reference_id": "YOUR_APPROVED_SIGNATURE_REFERENCE_ID",
      "comparison_reference": "YOUR_ACTUAL_COMPARISON_RESULT_REFERENCE",
      "verified_by": "YOUR_COMPARISON_SERVICE_OR_REVIEWER"
    }
  ]
}
```

Replace every placeholder with actual verified data; NIK must contain exactly 16 digits. Allowed statuses are `matched`, `mismatched`, and `unknown`. The result must match **both the actual extraction ID and the card's exact NIK**. A record for another job is ignored; a same-job conflicting NIK or duplicate records requires review. A matching `mismatched` record fails. A matched reference cannot override blank/corrupted/cropped signature failures.

Keep this JSON under your trusted application's control. Do not create verification records from OCR output, document wording or an unverified user assertion. The comparison record is retained in the audit output. Use `--validation-context` for single-file replay, or `--ektp-validation-context` for batch processing. For new jobs, obtain their actual IDs first, complete the external comparison, and replay the saved extraction without another billable job:

```powershell
python run.py --document-type ektp --replay "C:\outputs\extract_response.json" --validation-context "C:\data\signature-comparisons.json" --policy "C:\config\ektp-policy.json"
```

Photo validation checks portrait presence, face visibility and whether the **face** is cropped. Normal shoulder/body framing is not automatically a cropped face. It does not identify a person, compare the portrait to a selfie, or infer demographic traits. These are model-extracted observations, not a separate pixel detector; live quality must be assessed against actual card scans.

## Linked stamp requirement number 6

The supplied [Drive folder](a reference configured in the profile policy) could not be read when adding this profile. Its content and requirement number 6 are therefore **not inferred**. `policy.json` retains the reference URL and requirement number. Default `stamp_rule_confirmed=false`, `stamp_required=null` produces **`STAMP_REQUIREMENT_NUMBER_6_NOT_CONFIGURED`** and REVIEW without assuming every eKTP requires an ink stamp.

Once the actual criterion is available, configure the applicable visible presence/text checks in a copy of the full policy, for example:

```json
{
  "stamp_rule_confirmed": true,
  "stamp_required": true,
  "required_stamp_text_fragments": ["YOUR_ACTUAL_REQUIRED_TEXT"]
}
```

This snippet is an example, **not the contents of requirement number 6**, and is not a full policy file. If the confirmed criterion permits absence, set `stamp_required=false` and `required_stamp_text_fragments=[]`; an inspected absent stamp becomes NOT_APPLICABLE. A required stamp that is missing, cropped/unreadable or lacks required text fails. Text checks ignore case and redundant spaces.

If the actual rule requires authenticity/security checks beyond these visible criteria, extend the validator with your trusted verification result; presence/text checks alone cannot establish authenticity. Do not mark the rule confirmed merely to remove REVIEW.

Batch overrides:

```powershell
.\run_batch.bat --env-file .env --ektp-policy "C:\config\ektp-policy.json" --ektp-validation-context "C:\data\signature-comparisons.json"
```

## Offline example and tests

`examples/example_extract_response.json` contains **synthetic observations**, not OCR results from an actual card. Run immediately without an API key:

```bash
python run.py --document-type ektp --replay ektp/examples/example_extract_response.json --as-of 2026-10-05
```

It exports all twenty columns and reports REVIEW for the missing signature comparison and unconfigured stamp rule. Inspect schema and requests without uploading:

```bash
python run.py --document-type ektp --dry-run
```

The 28 eKTP tests cover all fields, exact NIK preservation, zero-padding, enum errors, multilingual dates, lifetime/dated validity, separate issuance data, signature/photo failures and uncertainty, job/NIK-bound reference comparisons, configurable stamp criteria, confidence and replay/export. Batch tests also exercise routing and separate eKTP summaries, along with actual SDK calls using mocked responses across all six profiles. No live extraction or biometric accuracy is claimed without your actual card PDF and API key.
