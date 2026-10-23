"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="error-page">
      <h1>Something interrupted this view.</h1>
      <p>Your accepted document processing continues in the background.</p>
      <button className="primary" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
