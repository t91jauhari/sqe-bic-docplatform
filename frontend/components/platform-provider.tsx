"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { api, setCsrf, uploadFiles } from "@/lib/api";
import type { User } from "@/lib/types";

type Toast = { id: number; message: string; tone: "success" | "error" };
type UploadState = { progress: number; label: string; active: boolean };
type Context = {
  user: User | null;
  loading: boolean;
  online: boolean;
  toasts: Toast[];
  upload: UploadState | null;
  notify: (message: string, tone?: "success" | "error") => void;
  dismiss: (id: number) => void;
  signIn: (
    organization: string,
    email: string,
    password: string,
  ) => Promise<void>;
  signOut: () => Promise<void>;
  startUpload: (
    form: FormData,
    key: string,
  ) => Promise<{ batch_id: string; case_ids: string[] }>;
};
const PlatformContext = createContext<Context | null>(null);

export function PlatformProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [online, setOnline] = useState(true);
  const [toasts, setToasts] = useState<Toast[]>([]),
    [upload, setUpload] = useState<UploadState | null>(null);
  const notify = useCallback(
    (message: string, tone: "success" | "error" = "success") => {
      const id = Date.now() + Math.random();
      setToasts((previous) =>
        previous.some((item) => item.message === message && item.tone === tone)
          ? previous
          : [...previous.slice(-2), { id, message, tone }],
      );
    },
    [],
  );
  const dismiss = useCallback(
    (id: number) =>
      setToasts((previous) => previous.filter((x) => x.id !== id)),
    [],
  );
  useEffect(() => {
    let alive = true;
    api<{ user: User; csrf: string }>("/auth/session")
      .then((data) => {
        if (alive) {
          setUser(data.user);
          setCsrf(data.csrf);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    const expired = () => {
      setUser(null);
      notify("Session expired. Sign in again; processing continues.", "error");
    };
    const down = () => setOnline(false),
      up = () => setOnline(true);
    window.addEventListener("session-expired", expired);
    window.addEventListener("offline", down);
    window.addEventListener("online", up);
    return () => {
      alive = false;
      window.removeEventListener("session-expired", expired);
      window.removeEventListener("offline", down);
      window.removeEventListener("online", up);
    };
  }, [notify]);
  const signIn = async (
    organization: string,
    email: string,
    password: string,
  ) => {
    const data = await api<{ user: User; csrf: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ organization, email, password }),
    });
    setCsrf(data.csrf);
    setUser(data.user);
  };
  const signOut = async () => {
    await api("/auth/logout", { method: "POST" });
    setCsrf("");
    setUser(null);
  };
  const startUpload = async (form: FormData, key: string) => {
    setUpload({ progress: 0, label: "Uploading documents", active: true });
    try {
      const result = await uploadFiles(form, key, (progress) =>
        setUpload({
          progress,
          label:
            progress === 100
              ? "Accepting and grouping documents"
              : "Uploading documents",
          active: true,
        }),
      );
      setUpload({
        progress: 100,
        label: "Documents accepted · workers continue in the background",
        active: false,
      });
      notify(
        result.case_ids.length + " customer case(s) queued for classification.",
      );
      return result;
    } catch (error) {
      setUpload(null);
      throw error;
    }
  };
  return (
    <PlatformContext.Provider
      value={{
        user,
        loading,
        online,
        toasts,
        upload,
        notify,
        dismiss,
        signIn,
        signOut,
        startUpload,
      }}
    >
      {children}
    </PlatformContext.Provider>
  );
}
export function usePlatform() {
  const ctx = useContext(PlatformContext);
  if (!ctx) throw new Error("Platform provider missing");
  return ctx;
}
export function useData<T>(path: string, interval = 5000) {
  const [snapshot, setSnapshot] = useState<{
      path: string;
      value: T;
      at: number;
    } | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const inflight = useRef<{ path: string; id: number } | null>(null),
    sequence = useRef(0),
    mounted = useRef(true),
    latestPath = useRef(path);
  latestPath.current = path;
  const refresh = useCallback(async () => {
    if (inflight.current?.path === path) return;
    const id = ++sequence.current;
    inflight.current = { path, id };
    try {
      const value = await api<T>(path);
      if (
        mounted.current &&
        latestPath.current === path &&
        id === sequence.current
      ) {
        setSnapshot({ path, value, at: Date.now() });
        setError("");
      }
    } catch (e) {
      if (
        mounted.current &&
        latestPath.current === path &&
        id === sequence.current
      )
        setError(e instanceof Error ? e.message : "Unable to load data.");
    } finally {
      if (inflight.current?.id === id) inflight.current = null;
      if (
        mounted.current &&
        latestPath.current === path &&
        id === sequence.current
      )
        setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    mounted.current = true;
    setLoading(true);
    setError("");
    void refresh();
    const timer = interval
      ? setInterval(() => {
          if (document.visibilityState === "visible") void refresh();
        }, interval)
      : undefined;
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    window.addEventListener("online", focus);
    return () => {
      mounted.current = false;
      if (timer) clearInterval(timer);
      window.removeEventListener("focus", focus);
      window.removeEventListener("online", focus);
    };
  }, [refresh, interval]);
  return {
    data: snapshot?.path === path ? snapshot.value : null,
    error,
    loading,
    lastUpdated: snapshot?.path === path ? snapshot.at : null,
    refresh,
  };
}
