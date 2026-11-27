import { useCallback, useEffect, useRef, useState } from "react";
import { errorText, request } from "../../shared/api/client";
import type { Account, RequestFeed } from "../../shared/types";

export function useRequests(
  active: Account | undefined,
  period: string,
  date: string,
  paused: boolean,
  priceRevision: number,
) {
  const identity = active
    ? `${active.name}:${active.updated_at}:${active.pending_apply}`
    : "";
  const key = `${identity}:${period}:${date}:${priceRevision}`;
  const context = useRef(key);
  context.current = key;
  const live = useRef(true);
  const inFlight = useRef(new Set<string>());
  const [feed, setFeed] = useState<{ key: string; value: RequestFeed } | null>(
    null,
  );
  const [failure, setFailure] = useState<{ key: string; value: string } | null>(
    null,
  );
  const [loadingKey, setLoadingKey] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!identity || inFlight.current.has(key)) return;
    inFlight.current.add(key);
    setLoadingKey(key);
    const params = new URLSearchParams({ period, limit: "100" });
    if (period === "date") params.set("date", date);
    try {
      const result = await request<RequestFeed>(`/api/requests?${params}`);
      if (live.current && context.current === key) {
        if (!result.result) throw new Error("未收到请求记录");
        setFeed({ key, value: result.result });
        setFailure(null);
      }
    } catch (error) {
      if (live.current && context.current === key)
        setFailure({ key, value: errorText(error) });
    } finally {
      inFlight.current.delete(key);
      if (live.current && context.current === key) setLoadingKey(null);
    }
  }, [key, identity, period, date]);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  useEffect(() => {
    if (paused || !identity) return;
    if (!document.hidden) void refresh();
    const interval = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 1000);
    return () => clearInterval(interval);
  }, [identity, paused, refresh]);

  return {
    feed: feed?.key === key ? feed.value : null,
    error: failure?.key === key ? failure.value : "",
    loading: loadingKey === key,
    refresh,
  };
}
