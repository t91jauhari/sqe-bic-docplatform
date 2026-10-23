"use client";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";
import { usePlatform } from "./platform-provider";

function ToastNotice({
  id,
  message,
  tone,
}: {
  id: number;
  message: string;
  tone: "success" | "error";
}) {
  const { dismiss } = usePlatform();
  const remaining = useRef(tone === "error" ? 10000 : 5000);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (hovered || focused) return;
    const started = Date.now();
    const timer = window.setTimeout(() => dismiss(id), remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(
        0,
        remaining.current - (Date.now() - started),
      );
    };
  }, [id, dismiss, hovered, focused]);
  return (
    <div
      className={"toast " + tone}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setFocused(false);
      }}
    >
      {tone === "error" ? (
        <AlertCircle size={18} aria-hidden />
      ) : (
        <CheckCircle2 size={18} aria-hidden />
      )}
      <span>{message}</span>
      <button aria-label="Dismiss notification" onClick={() => dismiss(id)}>
        <X size={16} />
      </button>
    </div>
  );
}

export function ToastNotifications() {
  const { toasts } = usePlatform();
  return (
    <div
      className="toasts"
      role="status"
      aria-live="polite"
      aria-relevant="additions"
    >
      {toasts.map((toast) => (
        <ToastNotice key={toast.id} {...toast} />
      ))}
    </div>
  );
}
