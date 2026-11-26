import type { RequestApi } from "./types";

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
export const tokens = (n?: number) =>
  n == null
    ? "—"
    : Math.abs(n) >= 1e6
      ? `${(n / 1e6).toFixed(2)}M`
      : Math.abs(n) >= 1e3
        ? `${(n / 1e3).toFixed(1)}K`
        : n.toLocaleString("en-US");
export const money = (n?: number, digits = 3) =>
  n == null
    ? "—"
    : `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
export const localDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};
