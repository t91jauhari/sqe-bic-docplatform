"use client";
import type { Document } from "@/lib/types";

export function FieldCrops({
  document,
  paths,
}: {
  document: Document;
  paths: string[];
}) {
  const fields = paths
    .filter((path) => path.startsWith(document.doc_type + "."))
    .map((path) => path.slice(document.doc_type.length + 1));
  const relevant = (field: string) =>
    fields.some((root) => field === root || field.startsWith(root + "."));
  const crops = [
    ...(document.validation.visual_evidence || [])
      .filter(
        (entry) =>
          relevant(entry.field) && entry.available && entry.storage_key,
      )
      .map((entry) => ({ ...entry, field: entry.field })),
    ...(document.validation.field_evidence || [])
      .filter((entry) => relevant(entry.field))
      .flatMap((entry) =>
        entry.crops.map((crop) => ({ ...crop, field: entry.field })),
      ),
  ];
  if (!crops.length)
    return (
      <p className="review-crop-note">
        No localized field crop is available for this check yet. Inspect the
        original page below.
      </p>
    );
  return (
    <div className="review-field-crops">
      <strong>Focused field crops</strong>
      <p>
        Check these regions against the full page below. A crop locates
        evidence; it does not approve the check.
      </p>
      <div>
        {crops.map((crop, index) => {
          const imageId = crop.storage_key
            ?.split("/")
            .pop()
            ?.slice(crop.revision.length + 1, -4);
          if (!imageId) return null;
          return (
            <figure key={`${crop.revision}-${imageId}-${index}`}>
              <a
                href={`/api/documents/${document.id}/file#page=${crop.page_number}`}
                target="_blank"
                rel="noreferrer"
              >
                <img
                  loading="lazy"
                  src={`/api/documents/${document.id}/evidence/${crop.revision}/${imageId}`}
                  alt={`${crop.field}, original page ${crop.page_number}`}
                />
              </a>
              <figcaption>
                {crop.field.replaceAll("_", " ")} · Page {crop.page_number}
              </figcaption>
            </figure>
          );
        })}
      </div>
    </div>
  );
}
