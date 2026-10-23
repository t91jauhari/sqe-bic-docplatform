# Forex SOP implementation — contract version 2

The 15 supplied checkpoints now use deterministic comparisons over stored extraction. There are no model calls or changes to extraction prompts, schemas, values, grouping or provider handling in this update.

| Checkpoint | Executable rule |
|---|---|
| 1 | eKTP full name equals application sender name; case and whitespace are cosmetic. No fuzzy name matching. |
| 2 | eKTP and Valas 1 name, address and 16-digit text NIK agree. NIK applicability requires explicit identity context. |
| 3 | eKTP full name equals RIPLAY customer name. |
| 4 | RIPLAY document date equals application date as a calendar date. |
| 5 | Compare both signature images through the existing audited visual review workspace. Presence alone never establishes visual consistency. |
| 6 | Application sender equals applicable Valas customer. Beneficiary is a separate role checked by 7 and 14. |
| 7 | Application beneficiary name AND address equal LLD recipient name/address. |
| 8 | Application principal amount AND currency equal LLD value; debit totals including fees are not substituted. |
| 9 | Valas 1 usage purpose agrees with application purpose through an explicit approved vocabulary. |
| 10 | Valas 1 amount AND currency equal LLD value. |
| 11 | LLD amount AND currency equal the explicitly chosen full invoice, progress claim or documented partial payment. Partial amount cannot exceed the invoice and requires annotated source evidence. |
| 12 | LLD purpose agrees with Valas 1 purpose through an explicit approved vocabulary. |
| 13 | LLD and application transaction dates are equal. |
| 14 | Invoice number is readable; invoice buyer matches sender and invoice payee (seller fallback) matches LLD beneficiary. An optional separate supporting invoice must match invoice number, full total and currency. LLD amount and currency must also match the selected invoice payment basis, using the same comparison as checkpoint 11. |
| 15 | LLD payer name equals eKTP full name. |

## Scoring and applicability

PASS earns 1; FAIL earns 0. Only image-based review can remain REVIEW (0 pending, included in possible points). Explicit NOT_APPLICABLE earns no point and is excluded from the denominator. Missing or ambiguous data fails, with a reason code and source document IDs. A Valas 2-only transaction explicitly excludes Valas 1-only checkpoints 2, 9, 10 and 12, unless above-threshold evidence requires Valas 1.

The new Forex package has 15 parent checkpoints. All applicable child fields must pass; missing configured checkpoints or compound child checks fail package compliance and show incomplete coverage. The existing full-rule score is preserved (18 atomic SOP3 checks plus any other configured rules). Release readiness, legacy regulatory scores, and package compliance remain separately labelled.

## Configuration and source selection

Settings → SOP checks → Forex comparison vocabulary exposes purpose codes, equivalent descriptions and address expansions. No regulatory purpose-code meanings are invented. The existing LLD purpose master is also respected. Case context supports explicit application/declaration/invoice selection; multiple candidates never trigger a search for whichever value passes. An optional separate supporting invoice can be selected. Document selections are restricted to completed documents of the correct type in the same case.

Names remain exact after Unicode/case/whitespace normalization. Address abbreviations and cosmetic punctuation can agree, but house/unit identifiers must still match. Amount parsing validates grouping, uses Decimal without tolerance or currency conversion, and requires a configured number locale for ambiguous separators. Numeric amount observations are already canonical. NIK must remain text to preserve leading zeros. Dates follow the document day-first policy and accept ISO dates.

## Compatibility and rollout

Run backend/scripts/enable_forex_sop_v2.py to publish the rules and policy idempotently. New cases use the published configuration. Existing cases keep pinned prompts and policy values; a compatibility adapter implements formerly unresolved checkpoints 6 and 14 on their next SOP run. The SOP contract fingerprint changes to version 2 so an explicit SOP rerun produces a new report from the same extraction. Historical report snapshots are untouched. New reports include sop_packages in JSON, a Forex SOP Package Excel sheet, PDF checkpoint results, and on-screen package scores.

Purpose meanings not established in approved configuration, unsupported partial-payment claims, conflicting source values and unselected document ambiguity continue to fail. These are data/evidence issues, not grounds to force a passing score.

## Verified locally

- Published configuration v39; API, worker and web built and running.
- 27 Forex acceptance tests and 23 platform tests passed. Regression checks covered Account Opening, document families, scoring, reviews, reporting, spatial evidence, field reprocessing and prompt delivery. Existing tests were updated for equivalent date formats and the earlier bounding-box schema/page-crop feature.
- Read-only evaluation of 38 existing Forex cases completed without evaluation errors. Published extraction profiles, provider settings, flows and other settings were unchanged.
- Sri P SOP-only rerun produced report v12 with identical raw, normalized and corrected extraction values. Its package remains 1/11 applicable points, 9 failed, 1 pending visual review and 4 not applicable; source gaps and mismatches remain visible.
- Live Excel export contained 15 checkpoint rows. PDF and JSON exports contained the Forex package.
