"use client";
import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("View Error Boundary caught:", error);
  }, [error]);

  return (
    <main className="error-page">
      <h1>Something interrupted this view.</h1>
      <p>Your accepted document processing continues in the background.</p>
      {error?.message && (
        <p
          style={{
            color: "#b91c1c",
            fontSize: "0.85rem",
            maxWidth: 600,
            wordBreak: "break-word",
            marginTop: 8,
          }}
        >
          {error.message}
        </p>
      )}
      <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
        <button className="primary" onClick={reset}>
          Try again
        </button>
        <button className="secondary" onClick={() => window.location.reload()}>
          Reload page
        </button>
      </div>
    </main>
  );
}
