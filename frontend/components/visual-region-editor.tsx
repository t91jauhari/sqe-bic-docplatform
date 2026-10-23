"use client";
import { useCallback, useEffect, useState } from "react";
import { Modal } from "@/components/ui";
import { api } from "@/lib/api";
export function VisualRegionEditor({
  documentId,
  field,
  onSaved,
}: {
  documentId: string;
  field: string;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false),
    [page, setPage] = useState(1),
    [zoom, setZoom] = useState(100),
    [loaded, setLoaded] = useState(false),
    [start, setStart] = useState<[number, number] | null>(null),
    [box, setBox] = useState<number[] | null>(null),
    [reason, setReason] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [learn, setLearn] = useState(true);
  useEffect(() => {
    setOpen(false);
    setPage(1);
    setZoom(100);
    setLoaded(false);
    setStart(null);
    setBox(null);
    setReason("");
    setError("");
    setLearn(true);
  }, [documentId, field]);
  const close = useCallback(() => setOpen(false), []);
  function point(e: React.PointerEvent<HTMLDivElement>): [number, number] {
    const r = e.currentTarget.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
    ];
  }
  async function save() {
    if (!box) return;
    setBusy(true);
    setError("");
    try {
      await api(`/documents/${documentId}/visual-box`, {
        method: "POST",
        body: JSON.stringify({
          field,
          page_number: page,
          bbox: box,
          reason,
          learn_for_future: learn,
        }),
      });
      setOpen(false);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button className="text-link" onClick={() => setOpen(!open)}>
        Select evidence region
      </button>
      {open && (
        <Modal className="document-region-modal" title={`Evidence region · ${field}`} onClose={close}>
          <p>
            Choose the page, then drag around the field value, visual mark, or
            inspected blank region.
          </p>
          <label>
            Page{" "}
            <input
              type="number"
              min={1}
              value={page}
              onChange={(e) => {
                setPage(Math.max(1, Math.floor(Number(e.target.value) || 1)));
                setLoaded(false);
                setError("");
                setBox(null);
              }}
            />
          </label>
          <div className="document-zoom-controls">
            <button disabled={zoom <= 50} onClick={() => setZoom(Math.max(50, zoom - 25))}>Zoom out</button>
            <output aria-live="polite">{zoom}%</output>
            <button disabled={zoom >= 250} onClick={() => setZoom(Math.min(250, zoom + 25))}>Zoom in</button>
            <button onClick={() => setZoom(100)}>Fit width</button>
          </div>
          <div className="document-page-viewport">
          <div
            style={{
              position: "relative",
              width: `${zoom}%`,
              margin: "0 auto",
              touchAction: "none",
              cursor: "crosshair",
            }}
            onPointerDown={(e) => {
              if (!loaded || e.button !== 0) return;
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              setStart(point(e));
              setBox(null);
            }}
            onPointerMove={(e) => {
              if (start && e.buttons) {
                const p = point(e);
                setBox([
                  Math.min(start[0], p[0]),
                  Math.min(start[1], p[1]),
                  Math.max(start[0], p[0]),
                  Math.max(start[1], p[1]),
                ]);
              }
            }}
            onPointerUp={() => setStart(null)}
            onPointerCancel={() => setStart(null)}
          >
            <img
              key={page}
              onLoad={() => setLoaded(true)}
              onError={() => { setLoaded(false); setError("Unable to load this page. Check the page number and try again."); }}
              alt={`Original page ${page}`}
              draggable={false}
              style={{ display: "block", width: "100%" }}
              src={`/api/documents/${documentId}/pages/${page}`}
            />
            {box && (
              <div
                style={{
                  position: "absolute",
                  pointerEvents: "none",
                  border: "2px solid #167f66",
                  background: "#167f6622",
                  left: `${box[0] * 100}%`,
                  top: `${box[1] * 100}%`,
                  width: `${(box[2] - box[0]) * 100}%`,
                  height: `${(box[3] - box[1]) * 100}%`,
                }}
              />
            )}
          </div>
          </div>
          <label>
            Review reason{" "}
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <label>
            <input
              type="checkbox"
              checked={learn}
              onChange={(e) => setLearn(e.target.checked)}
            />{" "}
            Use this reviewed region as guidance for future matching forms in
            this branch
          </label>
          <p>
            Future documents are checked independently. Changed or uncertain
            layouts keep their normal extraction and evidence review.
          </p>
          {error && <p role="alert">{error}</p>}
          <button
            disabled={busy || !box || reason.trim().length < 5}
            onClick={save}
          >
            {busy ? "Saving…" : "Save evidence and rerun SOP"}
          </button>
        </Modal>
      )}
    </div>
  );
}
