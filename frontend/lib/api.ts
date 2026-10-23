let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...init,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Connection unavailable. Your accepted jobs keep running; reconnect to refresh.",
    );
  }
  const data = await response
    .json()
    .catch(() => ({ detail: "Request could not be completed." }));
  if (!response.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "Please check the supplied values.";
    if (response.status === 401 && path !== "/auth/login" && csrf)
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(response.status, detail);
  }
  return data as T;
}
export function uploadFiles(
  form: FormData,
  key: string,
  onProgress: (value: number) => void,
) {
  return new Promise<{ batch_id: string; case_ids: string[] }>(
    (resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/uploads");
      xhr.withCredentials = true;
      xhr.setRequestHeader("X-CSRF-Token", csrf);
      xhr.setRequestHeader("Idempotency-Key", key);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        let data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = { detail: "Upload interrupted." };
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else
          reject(
            new ApiError(
              xhr.status,
              typeof data.detail === "string"
                ? data.detail
                : "Upload could not be accepted.",
            ),
          );
      };
      xhr.onerror = () =>
        reject(
          new ApiError(
            0,
            "Upload connection interrupted. Retry uses the same upload key.",
          ),
        );
      xhr.send(form);
    },
  );
}
