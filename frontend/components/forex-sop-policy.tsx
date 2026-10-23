"use client";
import type { Configuration, ForexSOPPolicy } from "@/lib/types";

export function ForexSOPPolicyEditor({
  draft,
  update,
  editable,
}: {
  draft: Configuration;
  update: (value: Partial<Configuration>) => void;
  editable: boolean;
}) {
  const policy: ForexSOPPolicy = draft.forex_sop_policy || {
    purpose_codes: {},
    purpose_equivalences: {},
    address_aliases: {},
  };
  const change = (key: keyof ForexSOPPolicy, value: unknown) =>
    update({ forex_sop_policy: { ...policy, [key]: value } });
  return (
    <section className="panel settings-card">
      <h2>Forex comparison vocabulary</h2>
      <p>
        Use approved definitions only. These settings affect SOP comparison,
        without changing extracted document values. Publish settings to apply changes to new cases; existing cases keep their pinned configuration.
      </p>
      <details>
        <summary>
          Configure purpose codes, equivalent phrases and address abbreviations
        </summary>
        <fieldset disabled={!editable}>
          <h3>Purpose codes</h3>
          <p className="subtext">
            A code is equivalent to a description only when mapped here or in
            the LLD purpose master. No regulatory code meaning is assumed.
          </p>
          {Object.entries(policy.purpose_codes).map(([code, description]) => (
            <div className="form-grid" key={code}>
              <label>
                Code
                <input value={code} readOnly />
              </label>
              <label>
                Approved description
                <input
                  value={description}
                  onChange={(e) =>
                    change("purpose_codes", {
                      ...policy.purpose_codes,
                      [code]: e.target.value,
                    })
                  }
                />
              </label>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  const values = { ...policy.purpose_codes };
                  delete values[code];
                  change("purpose_codes", values);
                }}
              >
                Remove code {code}
              </button>
            </div>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              const code = String(data.get("code") || "").trim(),
                description = String(data.get("description") || "").trim();
              if (code && description && !(code in policy.purpose_codes)) {
                change("purpose_codes", {
                  ...policy.purpose_codes,
                  [code]: description,
                });
                e.currentTarget.reset();
              }
            }}
          >
            <div className="form-grid">
              <label>
                New purpose code
                <input name="code" required maxLength={500} />
              </label>
              <label>
                Approved description
                <input name="description" required maxLength={500} />
              </label>
            </div>
            <button className="secondary">Add purpose mapping</button>
          </form>
          <h3>Equivalent purpose descriptions</h3>
          <p className="subtext">
            One phrase per line within a group. Only explicitly listed phrases
            share a meaning.
          </p>
          {Object.entries(policy.purpose_equivalences).map(
            ([group, phrases]) => (
              <label key={group}>
                {group.replaceAll("_", " ")}
                <textarea
                  rows={5}
                  value={phrases.join("\n")}
                  onChange={(e) =>
                    change("purpose_equivalences", {
                      ...policy.purpose_equivalences,
                      [group]: e.target.value.split("\n"),
                    })
                  }
                />
              </label>
            ),
          )}
          <h3>Address abbreviations</h3>
          <p className="subtext">
            Expand known abbreviations. House numbers and unit identifiers must
            still match exactly.
          </p>
          <div className="form-grid">
            {Object.entries(policy.address_aliases).map(([alias, value]) => (
              <label key={alias}>
                {alias}
                <input
                  value={value}
                  onChange={(e) =>
                    change("address_aliases", {
                      ...policy.address_aliases,
                      [alias]: e.target.value,
                    })
                  }
                />
              </label>
            ))}
          </div>
        </fieldset>
      </details>
    </section>
  );
}
