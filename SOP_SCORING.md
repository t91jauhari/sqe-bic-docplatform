# Shared SOP scoring

All document families use the same evaluator outcome contract, including Forex, Account Opening and configurable families.

Each enabled applicable rule earns 1 for PASS and 0 for FAIL. Only registered visual operators or visual field checks can remain REVIEW. Unresolved data checks fail with INSUFFICIENT_OR_UNVERIFIED_DATA; this indicates missing or unreliable evidence, not a confirmed mismatch. Correct data/context and rerun SOP.

Explicit applicability exclusions are NOT_APPLICABLE and excluded. Absent source documents alone do not exclude a rule. Pending visual reviews remain in possible points and make the percentage provisional. Audited visual observations resolve them to PASS or FAIL.

Snapshots store sop_summary separately from legacy category compliance indicators (scores). The latter preserve existing fixed report layouts and must not be counted as individual checks. Excel adds SOP Rule Points and SOP Point Detail sheets; PDF, JSON and application report pages expose the new summary. Release readiness remains separate from the percentage.

Legacy review bypass settings remain readable for historic configuration compatibility but have no effect on the new evaluator. Manual review accepts visual findings only. Historical snapshots are unchanged. Use Rerun SOP checks to create a current result from stored extraction without model calls. Input fingerprints include sop_contract_version so the new contract is evaluated even if document values have not changed.
