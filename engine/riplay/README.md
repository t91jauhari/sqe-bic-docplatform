# RIPLAY Document — four-page profile

Ten fields follow the supplied column list exactly. Run from the engine directory:

    python run.py --document-type riplay --pdf samples/customer_riplay.pdf --parse-tier agentic_plus --extract-tier agentic_plus

Or use run_riplay.bat on Windows / bash run_riplay.sh on Linux. The attached sample is included under the filename above. Configure the existing LlamaCloud API key in engine/.env as for the other profiles. No API key is included in this package.

Inspect configuration without cloud calls:

    python run.py --document-type riplay --dry-run --output outputs/riplay-dry-run

Replay synthetic evidence without API credits:

    python run.py --document-type riplay --replay riplay/examples/example_extract_response.json --validation-context riplay/validation_context.example.json --output outputs/riplay-replay

The example JSON and reference comparisons are synthetic, not extraction of the attached sample. Default unconfigured stamp rules still require review.

## Fields and evidence

| Field | Extraction focus |
| --- | --- |
| document_place | Entered city beside execution date |
| document_date | Execution/creation date, distinct from print date |
| bank_officer_name | Readable full-name entry, not a guessed signature identity |
| bank_officer_signature | Officer's labelled signature region |
| customer_name | Readable customer full-name entry |
| customer_signature | Customer's labelled signature region |
| printed_date | Explicit Tanggal Cetak Dokumen / Printed Date |
| page_initials | Agreement initials at bottom right of pages 1–3; page 4 has the main signing block |
| customer_stamp | Requirement 18, customer's signing region |
| cs_stamp | Requirement 5, bank officer's signing region |

Product descriptions, examples, disclaimers, logos, footer regulatory wording and PDF metadata cannot supply these values. Parsing preserves page boundaries, final-page signing columns and footer margins. Extraction returns raw text and visible evidence; local validation normalizes dates to DD-MM-YYYY and preserves raw extraction.

Names allow letters, spaces, dots and straight/curly apostrophes. City must contain letters. Dates must be valid and not future dated; print date must be at least the creation date. Signatures must be present, handwritten/non-text, complete and uncorrupted. Signature correspondence is a separate reference check; OCR visibility cannot prove who signed.

All four physical pages need unique inspection records. Only pages 1–3 require bottom-right customer agreement initials (`required_initial_pages: [1, 2, 3]`). Page 4 has the main signing fields and requires no separate footer initial. A page-4 main signature cannot replace an initial on pages 1–3.

## Identity, signatures and stamp requirements

Standalone runs accept trusted eKTP name and signature-comparison records via --validation-context. The example specifies required keys; signature comparisons bind to extraction job ID, field/page and signer name. Unknown/missing comparisons produce REVIEW; explicit mismatch produces FAIL. Do not use synthetic comparisons as real verification.

Platform processing automatically compares RIPLAY customer_name to one completed, readable eKTP name in the same case. Only case/whitespace normalization is allowed; no fuzzy overwrite. Missing/multiple/unreadable reference yields REVIEW. A later eKTP completion updates the case finding automatically. Raw identities remain unchanged. Platform-native validation marks the identity check as pending the case SOP checker; standalone validation requires a trusted reference. The current platform has no signature-comparison connector, so signature correspondence remains REVIEW by default. Setting require_signature_comparison=false disables that rule explicitly; it does not verify authenticity.

Stamp requirements 18 and 5 were linked to an inaccessible reference folder. Each has independent rule_confirmed, required and text_fragments settings in policy.json / platform Configuration. Default is unconfigured → REVIEW. Configured required stamps must be visible, legible and located at the correct signer. Pixel/OCR observations do not certify authenticity.

## Batch and platform support

Use customer-name_riplay.pdf. Batch discovery includes *_riplay.pdf, with one result.csv per source and a separate riplay_result.csv summary. Other document types keep their own CSVs. --riplay-policy and --riplay-validation-context provide batch-specific overrides.

The platform groups by filename customer first, then LlamaCloud Classify selects/verifies the RIPLAY schema. New uploads use the latest configuration. Development startup adds RIPLAY as a new configuration version, preserving custom settings and historical case versions. In other deployments run backend/migrate_profiles.py with API/workers stopped before restart. Old cases remain pinned and cannot process a newly added profile without an explicit configuration migration; create a new case using the new version.

## Attached sample observations

The supplied PDF contains four pages. Initials appear in bottom-right margins on pages 1–3; the main customer/officer execution block is on page 4. The labelled print date is 31 Mei 2023 while entered execution date is 25/08/2025. The supplied print-date rule therefore produces PRINT_DATE_BEFORE_DOCUMENT_DATE; the implementation does not change either date to force a pass. Page 4 does not require a separate bottom-right initial. Names and stamp contents require actual cloud extraction/reviewer evidence; the filename is not ground truth.

A successful extraction still writes outputs when validation is FAIL or REVIEW, matching the other profiles. No live paid LlamaCloud run of this sample has been performed in this environment.
