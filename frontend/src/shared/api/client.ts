import type { RequestApi } from "../types";

export const request: RequestApi = async (path, body, options) => {
  const response = await fetch(
    path,
    body === undefined
      ? { cache: "no-store", signal: options?.signal }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: options?.signal,
        },
  );
  const payload = await response.json();
  if (!response.ok || !payload.ok)
    throw new Error(payload.error || `请求失败（HTTP ${response.status}）`);
  return payload;
};

export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试";
