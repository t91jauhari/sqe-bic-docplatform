"use client";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
type Sample = {
  id: string;
  field: string;
  page_number: number;
  enabled: boolean;
  layout_available: boolean;
  reason: string;
};
export function LocationLearningHistory({
  documentType,
}: {
  documentType: string;
}) {
  const { data, error, refresh } = useData<Sample[]>(
    `/location-learning?document_type=${encodeURIComponent(documentType)}`,
    0,
  );
  const { user, notify } = usePlatform();
  const canReview = ["bank_admin", "branch_admin", "reviewer"].includes(
    user?.role || "",
  );
  async function disable(id: string) {
    try {
      await api(`/location-learning/${id}/disable`, { method: "POST" });
      await refresh();
      notify("Future reuse disabled. Saved evidence is retained.");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Unable to disable", "error");
    }
  }
  return (
    <section>
      <h3>Learned field locations</h3>
      <p>
        Reviewed locations guide future Parse and Extract jobs for matching
        forms. They never replace the new document’s own evidence. Changes apply
        to new jobs; existing jobs keep their recorded guidance.
      </p>
      {error && <p role="alert">{String(error)}</p>}
      {!data?.length && (
        <p>
          No reviewed location examples yet. Save an evidence region on a case
          to add one.
        </p>
      )}
      {!!data?.length && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Page</th>
                <th>Future reuse</th>
                <th>Reason</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id}>
                  <td>{s.field}</td>
                  <td>{s.page_number}</td>
                  <td>
                    {!s.enabled
                      ? "Disabled"
                      : s.layout_available
                        ? "Enabled for matching forms"
                        : "Recorded; layout unavailable"}
                  </td>
                  <td>{s.reason}</td>
                  <td>
                    {canReview && s.enabled && (
                      <button
                        className="secondary"
                        onClick={() => disable(s.id)}
                      >
                        Disable reuse
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
