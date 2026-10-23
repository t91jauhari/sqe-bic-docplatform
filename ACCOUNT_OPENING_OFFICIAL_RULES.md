# Account Opening official cross-document checks

Confirmed on 22 October 2026. EED in the supplied list means the existing EDD profile.

The package retains the official numbering. Rule 12 is excluded at the user's request. Rule 8 checks document CIF consistency only; external CBS verification is also excluded. Neither exclusion is represented as a successful external verification.

## Field mapping and implemented rules

| No. | Source field | Compared field | Implemented decision |
| --- | --- | --- | --- |
| 1 | `ektp.nik` — NIK | `account_opening_form.identity_number` — Nomor Identitas | Both values must contain exactly 16 digits and be identical. Leading zeros are preserved. |
| 2 | `ektp.name` — Nama | `account_opening_form.customer_name` — Nama Lengkap | Same spelling passes. Ordered initials or explicit dotted prefix abbreviations can pass only after an audited visual comparison of `ektp.owner_signature` and `account_opening_form.customer_signature`. A changed spelling, reordered name, or missing name token fails. Initials alone never auto-pass. |
| 3 | `ektp.birth_place` and `ektp.birth_date` | `account_opening_form.birth_place_date` — Tempat/Tanggal Lahir | Both place and explicit full date must match. Common comma/slash separators and Indonesian month names are supported. Missing components are not inferred from NIK. |
| 4 | `ektp.name` | `join_visit.customer_name` — Nama Nasabah | Same spelling is required. Rule 2's abbreviation exception does not apply here. |
| 5 | `ektp.gender` — Jenis Kelamin | `account_opening_form.gender` — Jenis Kelamin | Laki-laki maps to Pria; Perempuan maps to Wanita. Unknown or conflicting values fail. |
| 6 | `ektp.citizenship` — Kewarganegaraan | `account_opening_form.citizenship` | Both must match and use WNI or WNA. Matching invalid text does not pass. |
| 7 | `ektp.occupation` — Pekerjaan | `account_opening_form.occupation` — Pekerjaan Utama | Exact occupation wording is required, as clarified by the user. DOSEN is not automatically equivalent to Pegawai Swasta. |
| 8 | `join_visit.cif` — CIF | `account_opening_form.cif` — Nomor CIF | Identical document values, including leading zeros. External CBS traceability is skipped by instruction. |
| 9 | `edd.cif` — Nomor CIF | `account_opening_form.cif` — Nomor CIF | Identical values, including leading zeros. The label's workbook field number is not used as a positional lookup. |
| 10 | `edd.customer_name` and `edd.occupation` — Nama and Informasi jabatan | `company_reference.customer_name` and `company_reference.customer_position` — Nama Nasabah and Jabatan Nasabah | Both name and customer job title must match verbatim. One official check earns one point only if both parts pass. `edd.edd_officer`, `edd.supervisor`, `company_reference.signatory_name` and `company_reference.signatory_position` are different people/roles and cannot substitute. |
| 11 | `signature_difference.customer_name` — Nama | `account_opening_form.customer_name` | Names must match. |
| 12 | `signature_difference.signature_one` and `signature_difference.signature_two` | External system specimen | Excluded by user instruction. No external specimen is invented, inferred from uploaded signatures, or treated as verified. |
| 13 | `riplay.customer_name` — Nasabah (Nama) | `account_opening_form.customer_name` | Names must match. The separate printed-name field is compared; a blank name is not filled from a signature or filename. |
| 14 | `company_reference.customer_name` — Nama Nasabah mentioned in the letter | `join_visit.customer_name` | Names must match. Employer signatory and transaction-confirmation contact names are not the customer field. |
| 15 | `ektp.name` | `company_reference.customer_name` | Customer names must match official identity. |

## Decision and scoring behavior

- Case and whitespace formatting differences do not change spelling. Literal identifiers retain every digit and leading zero. Names do not use fuzzy edit-distance matching.
- Automatic data checks produce PASS or FAIL. Missing/ambiguous required data does not receive a pass.
- Rule 2 enters visual REVIEW only for a supported initial abbreviation. The reviewer must compare the two customer signature regions and record both document observations. Presence alone cannot establish a match, and unrelated name differences cannot be manually approved through this exception.
- PASS earns one point and FAIL earns zero. Pending visual decisions remain in the possible-point denominator. Rule 10's two components do not create two points.
- Existing optional/conditional supporting-document applicability and document-completeness controls remain in place. Excluded external verification does not add a point or a failed external lookup.

## Configuration and compatibility

The release marker is `account-opening-official-cross-document-v2`. Startup publishes an immutable configuration version updating the fourteen existing `AO_SYSTEM_*` definitions. It preserves enabled-state choices, other SOP rules, Forex rules, extraction profiles, provider configuration and pinned historical case versions.

No extraction field was added or renamed. No model extraction flow was changed. The visual review page includes the signature-support crop paths when rule 2 needs evidence. Existing cases retain their original configuration and reports; new cases use the published version.

The independent Spider document-validation bypass finding from the simulation is separate from this package correction and is not repaired by this change.
