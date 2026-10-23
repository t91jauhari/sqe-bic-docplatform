# Spatial grounding and source crops

All twelve existing document profiles received the requested section 6 in published configuration v38. New profile defaults and future configuration publications include it. The shared prompt compiler also includes it when an older pinned profile is used by a new extraction request. Existing frozen reports remain unchanged.

The transport keeps business values separate from source locations:

```json
{"name":"Example","_field_locations":[{"field":"name","page_number":1,"box_2d":[100,200,150,500]}]}
```

Coordinates are [ymin,xmin,ymax,xmax] in 0–1000 against the original full physical page. The adapter converts them to the crop pipeline's normalized [xmin,ymin,xmax,ymax]. A positive original page number and finite, ordered, in-bounds coordinates are required. Empty boxes are accepted as no evidence. Boxes for null/absent observations are not used. Inline visual box properties and value/box wrappers are supported without adding metadata to business values.

Spider sequential extraction merges business values independently from spatial metadata. Per-page provider observations remain available for replay; rejected/conflicting page values do not provide accepted field crops. Prior-page continuity context excludes coordinates. LlamaCloud receives an augmented transport schema with the reserved metadata array; editable business schemas are unchanged. Full extraction and targeted reprocessing use the shared instructions.

The existing original-page raster crop pipeline stores private PNG evidence and its source hash, extraction ID, field path, page and revision. Text/structured field crops populate Extracted field crops in case details; signatures, stamps, photos and page initials populate visual evidence. The dedicated review workspace displays matching focused crops and the original page together. Generated crops remain PENDING evidence, never an automatic review approval. Invalid coordinates remain unavailable with an explanation. Selected-field runs invalidate and regenerate selected evidence only and preserve other fields' crops.

All 222 existing completed extractions were checked and none contained box_2d. They have not been bulk re-extracted. New extraction or selected-field rereads can supply boxes; Generate / refresh field crops reuses saved locations and makes no model call. It cannot infer missing locations from old results.

Validation covers coordinate order, exact physical-page pixels, bounds/NaN/bool rejection, absent values, repeated values and table-row offsets across pages, prompt delivery to both providers, selected-field evidence preservation and schema workbook compatibility. No paid model calls were made during these checks; model localization precision still depends on the returned observations.
