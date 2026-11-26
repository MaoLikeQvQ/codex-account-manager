import { useCallback, useEffect, useRef, useState } from "react";
import { errorText, localDate, request } from "./api";
import type { AppState, Quota, RequestApi, Usage } from "./types";

export function useManager(modalOpen: boolean, priceRevision: number) {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(0);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [usageError, setUsageError] = useState("");
  const [usageLoading, setUsageLoading] = useState(false);
  const [period, setPeriod] = useState("today");
  const [date, setDate] = useState(localDate());
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [quotas, setQuotas] = useState<
    Record<string, { version: string; quota: Quota }>
  >({});
  const [quotaLoading, setQuotaLoading] = useState(false);
  const stateRequest = useRef(0);
  const usageRequest = useRef(0);
  const quotaRequest = useRef(0);
  const mutationPending = useRef(0);
  const live = useRef(true);
  const stateRef = useRef(state);
  stateRef.current = state;
  const active = state?.accounts.find((item) => item.active);
  // An edited/applied account with the same name is still a new usage context.
  const identity = active
    ? `${active.name}:${active.updated_at}:${active.pending_apply}`
    : "";

  const api = useCallback<RequestApi>(
    async <T = unknown>(path: string, body?: unknown, options?: { signal?: AbortSignal }) => {
      const mutating = body !== undefined;
      const sequence = ++stateRequest.current;
      if (mutating) {
        mutationPending.current++;
        setPending((n) => n + 1);
      }
      try {
        const response = await request<T>(path, body, options);
        if (live.current && response.data && sequence >= stateRequest.current) {
          setState(response.data);
          setError("");
          setUpdatedAt(new Date());
        }
        return response;
      } finally {
        if (mutating) {
          mutationPending.current--;
          if (live.current) setPending((n) => n - 1);
        }
      }
    },
    [],
  );

  const refreshState = useCallback(async () => {
    try {
      await api("/api/state");
    } catch (failure) {
      if (live.current) setError(errorText(failure));
    }
  }, [api]);

  const refreshUsage = useCallback(async () => {
    const current = stateRef.current?.accounts.find((item) => item.active);
    const id = ++usageRequest.current;
    if (!current) {
      setUsage(null);
      setUsageError("");
      setUsageLoading(false);
      return;
    }
    setUsageLoading(true);
    setUsageError("");
    const params = new URLSearchParams({ period });
    if (period === "date") params.set("date", date);
    try {
      const response = await request<Usage>(`/api/usage?${params}`);
      if (live.current && id === usageRequest.current)
        setUsage(response.result ?? null);
    } catch (failure) {
      if (live.current && id === usageRequest.current) {
        setUsage(null);
        setUsageError(errorText(failure));
      }
    } finally {
      if (live.current && id === usageRequest.current) setUsageLoading(false);
    }
  }, [period, date]);

  const acceptQuota = useCallback(
    (name: string, quota: Quota, expectedVersion?: string) => {
      const account = stateRef.current?.accounts.find(
        (item) => item.name === name,
      );
      if (
        !account ||
        account.account_type !== "official" ||
        (expectedVersion !== undefined &&
          account.updated_at !== expectedVersion)
      )
        return;
      setQuotas((previous) => ({
        ...previous,
        [name]: { version: account.updated_at, quota },
      }));
    },
    [],
  );
  const refreshQuota = useCallback(async () => {
    const current = stateRef.current?.accounts.find((item) => item.active);
    const id = ++quotaRequest.current;
    if (!current || current.account_type !== "official") {
      setQuotaLoading(false);
      return;
    }
    setQuotaLoading(true);
    try {
      const response = await request<Quota>(
        `/api/accounts/quota?name=${encodeURIComponent(current.name)}`,
      );
      if (live.current && id === quotaRequest.current && response.result)
        acceptQuota(current.name, response.result, current.updated_at);
    } catch (failure) {
      if (live.current && id === quotaRequest.current)
        acceptQuota(
          current.name,
          { errors: { request: errorText(failure) } },
          current.updated_at,
        );
    } finally {
      if (live.current && id === quotaRequest.current) setQuotaLoading(false);
    }
  }, [acceptQuota]);

  useEffect(() => {
    live.current = true;
    void refreshState();
    return () => {
      live.current = false;
      stateRequest.current++;
      usageRequest.current++;
      quotaRequest.current++;
    };
  }, [refreshState]);
  useEffect(() => {
    setUsage(null);
    void refreshUsage();
    return () => {
      usageRequest.current++;
    };
  }, [identity, refreshUsage, priceRevision]);
  useEffect(() => {
    void refreshQuota();
    return () => {
      quotaRequest.current++;
    };
  }, [identity, refreshQuota]);
  useEffect(() => {
    let running = false;
    let lastUsage = Date.now();
    const timer = setInterval(async () => {
      if (running || modalOpen || document.hidden || mutationPending.current)
        return;
      running = true;
      try {
        await refreshState();
        if (period === "today" && Date.now() - lastUsage >= 60000) {
          await refreshUsage();
          lastUsage = Date.now();
        }
      } finally {
        running = false;
      }
    }, 10000);
    return () => clearInterval(timer);
  }, [modalOpen, period, refreshState, refreshUsage]);

  return {
    state,
    active,
    api,
    busy: pending > 0,
    error,
    refreshState,
    usage,
    usageError,
    usageLoading,
    refreshUsage,
    period,
    setPeriod,
    date,
    setDate,
    updatedAt,
    quota:
      active?.account_type === "official" &&
      quotas[active.name]?.version === active.updated_at
        ? quotas[active.name].quota
        : undefined,
    quotaLoading,
    refreshQuota,
    acceptQuota,
  };
}
