# Document families

Open Configuration > Document families. Bank administrators can add a family
from an existing setup, then configure it in three sections:

1. Basics: name, purpose and availability for new cases.
2. Documents & extraction: registered document profiles, default required
   documents for new flows, family reading guidance and page-processing overrides.
3. Checks & reports: SOP checks, reference dataset, supported report layout
   and report headings for new flows.

Create a transaction flow in the family to make it available during upload.
New flows start from the family defaults unless explicitly duplicated from
another flow. Existing flows retain their configured requirements, checks,
dataset and layout. Test and publish the draft to activate changes.

Family guidance is combined with each selected profile's existing instructions
for ordinary extraction and field rereads. It is scoped to the case's family,
so it does not alter shared profiles in other families. Normal runs use the
case's pinned configuration; field rereads can use the latest configuration.
Shared profile fields and instructions remain editable under Document profiles.

Disabling a family prevents new cases through its flows. Existing cases and
their pinned versions remain available. Family definitions are included in
configuration workbook export/import and ordinary configuration versioning.

Families reuse registered extraction engines and the two existing report layouts;
adding a new family does not register a new document extraction engine or report
renderer. Connector credentials, access roles and workflow automation remain
shared platform settings in their existing configuration sections.
