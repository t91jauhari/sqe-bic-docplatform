"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  CheckCheck,
  Inbox as InboxIcon,
  AlertTriangle,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { Busy, Empty, ErrorNotice } from "@/components/ui";
import { formatWhen } from "@/lib/time";
import { api } from "@/lib/api";
import type { InboxItem } from "@/lib/types";
export default function Inbox() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, refresh } = useData<InboxItem[]>(
      `/inbox?offset=${offset}`,
    ),
    { notify } = usePlatform(),
    [filter, setFilter] = useState("unread"),
    [busy, setBusy] = useState(false);
  const rows =
    data?.filter((x) => {
      if (filter === "unread") return !x.read;
      if (filter === "urgent") return x.severity === "ERROR" || x.overdue;
      if (filter === "review") return x.severity === "REVIEW";
      return true;
    }) || [];
  const groups = [
    ...new Map(
      rows.map((item) => [
        item.case_id,
        rows.filter((x) => x.case_id === item.case_id),
      ]),
    ).values(),
  ].sort(
    (a, b) =>
      Number(b.some((x) => x.overdue)) - Number(a.some((x) => x.overdue)),
  );
  async function markRead(items: InboxItem[]) {
    setBusy(true);
    try {
      for (const item of items.filter((x) => !x.read))
        await api(`/inbox/${item.id}/read`, { method: "POST" });
      await refresh();
    } catch (e) {
      notify(
        e instanceof Error
          ? e.message
          : "Some notifications could not be marked read. Reload to check their status.",
        "error",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Shell
      title="Your inbox"
      subtitle="One place for case actions, processing exceptions and report readiness."
    >
      <div className="inbox-heading">
        <div className="pill-tabs">
          <button
            className={filter === "unread" ? "active" : ""}
            onClick={() => setFilter("unread")}
          >
            Unread <span>{data?.filter((x) => !x.read).length || 0}</span>
          </button>
          <button
            className={filter === "urgent" ? "active" : ""}
            onClick={() => setFilter("urgent")}
          >
            Urgent / Errors{" "}
            <span>
              {data?.filter((x) => x.severity === "ERROR" || x.overdue).length || 0}
            </span>
          </button>
          <button
            className={filter === "review" ? "active" : ""}
            onClick={() => setFilter("review")}
          >
            Needs review{" "}
            <span>{data?.filter((x) => x.severity === "REVIEW").length || 0}</span>
          </button>
          <button
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            All actions <span>{data?.length || 0}</span>
          </button>
        </div>
        <button
          className="text-link"
          disabled={busy || loading || !rows.some((x) => !x.read)}
          onClick={() => {
            if (
              confirm(
                "Mark all displayed notifications as read? This cannot be undone.",
              )
            )
              void markRead(rows);
          }}
        >
          {busy ? "Updating…" : "Mark displayed notifications read"}
        </button>
        <span className="muted">
          Reading an item does not resolve its case.
        </span>
      </div>
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      <p>
        {groups.length} cases in the displayed notification window.
        Notifications are grouped by case, with overdue cases first. Reading
        notifications does not approve findings or resolve cases.
      </p>
      <div className="button-row">
        <button
          disabled={busy || loading || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Newer notifications
        </button>
        <span>
          Notification window {offset + 1}–{offset + (data?.length || 0)}
        </span>
        <button
          disabled={busy || loading || (data?.length || 0) < 100}
          onClick={() => setOffset(offset + 100)}
        >
          Older notifications
        </button>
      </div>
      <section className="panel">
        {loading && !data ? (
          <Busy />
        ) : rows.length ? (
          <div className="inbox-list">
            {groups.map((items) => {
              const item = items[0];
              const errorCount = items.filter(
                (x) => x.severity === "ERROR" || x.overdue,
              ).length;
              const reviewCount = items.filter(
                (x) => x.severity === "REVIEW",
              ).length;
              const hasUrgency = errorCount > 0;
              const summary = [
                `${items.length} notification${items.length === 1 ? "" : "s"}`,
                reviewCount ? `${reviewCount} review finding${reviewCount === 1 ? "" : "s"}` : "",
                errorCount ? `${errorCount} processing error${errorCount === 1 ? "" : "s"}` : "",
              ].filter(Boolean);
              return (
                <article
                  key={item.case_id}
                  className={
                    (items.some((x) => !x.read) ? "unread " : "") +
                    (hasUrgency ? "urgent" : "")
                  }
                >
                  <div className="inbox-icon">
                    {hasUrgency ? (
                      <AlertTriangle size={20} className="urgent-icon" />
                    ) : (
                      <InboxIcon size={20} />
                    )}
                  </div>
                  <div className="inbox-content">
                    <Link href={`/cases/${item.case_id}`}>
                      <h3>{item.title}</h3>
                    </Link>
                    <p>
                      {summary.join(" · ")}
                      {items.some((x) => x.overdue) ? " · OVERDUE" : ""}
                    </p>
                    <details>
                      <summary>View notifications together</summary>
                      {items.map((x) => (
                        <div key={x.id}>
                          <strong>{x.title}</strong>
                          <p>{x.body}</p>
                          <small>
                            {formatWhen(x.created_at)} ·{" "}
                            {x.read ? "Read" : "Unread"}
                          </small>
                        </div>
                      ))}
                    </details>
                  </div>
                  <div className="inbox-actions">
                    <Link className="primary" href={`/cases/${item.case_id}`}>
                      Review case
                      <ArrowUpRight size={15} />
                    </Link>
                    {items.some((x) => !x.read) && (
                      <button
                        className="text-link"
                        disabled={busy || loading}
                        onClick={() => void markRead(items)}
                      >
                        <CheckCheck size={15} />
                        Mark case notifications read
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <Empty
            title={filter === "unread" && data?.length ? "No unread notifications in this window" : "No notifications in this window"}
            detail="Use All actions or navigate notification windows to check pending case actions. Read status does not indicate that a case is resolved."
          />
        )}
      </section>
    </Shell>
  );
}
