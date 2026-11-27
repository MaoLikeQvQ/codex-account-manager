import { useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import PersonOutlineRounded from "@mui/icons-material/PersonOutlineRounded";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import DnsOutlined from "@mui/icons-material/DnsOutlined";
import { errorText } from "../../shared/api/client";
import { money } from "../../shared/lib/format";

import type { Account, Quota, QuotaSnapshot, RequestApi } from "../../shared/types";

interface Props {
  account: Account;
  quota?: Quota;
  restartRequired: boolean;
  locked: boolean;
  api: RequestApi;
  onQuota: (quota: Quota) => void;
  onDetails: () => void;
  onActivate: () => void;
}

function resetLabel(timestamp?: number) {
  if (!timestamp || !Number.isFinite(timestamp)) return "重置时间未知";
  const minutes = Math.ceil((timestamp * 1000 - Date.now()) / 60000);
  if (minutes <= 0) return "等待重置";
  if (minutes < 60) return `${minutes} 分钟后重置`;
  if (minutes < 1440) return `${Math.ceil(minutes / 60)} 小时后重置`;
  return `${Math.ceil(minutes / 1440)} 天后重置`;
}

function CompactQuota({ quota, loading }: { quota?: Quota; loading: boolean }) {
  const limits = quota?.limits;
  const buckets: [string, QuotaSnapshot][] =
    limits?.rateLimitsByLimitId &&
    Object.keys(limits.rateLimitsByLimitId).length
      ? Object.entries(limits.rateLimitsByLimitId)
      : [["Codex", limits?.rateLimits || {}]];
  return (
    <Stack
      spacing={0.5}
      aria-label="账号配额"
      sx={{
        flexShrink: 0,
        width: 94,
        px: 0,
        py: 0.25,
      }}
    >
      {buckets.flatMap(([id, snapshot]) =>
        (["primary", "secondary"] as const).map((key) => {
          const window = snapshot[key];
          const known =
            typeof window?.usedPercent === "number" &&
            Number.isFinite(window.usedPercent);
          const remaining = known
            ? 100 - Math.max(0, Math.min(100, window.usedPercent!))
            : 0;
          const duration = window?.windowDurationMins;
          const label =
            duration === 300
              ? "5h"
              : duration === 10080
              ? "7d"
              : duration
              ? duration + "m"
              : key === "primary"
              ? "5h"
              : "7d";
          const amount = quota?.amount_estimate?.windows?.[id + ":" + key];
          const estimate =
            typeof amount?.remaining_usd === "number" &&
            Number.isFinite(amount.remaining_usd)
              ? "剩余预估 ≈ " + money(amount.remaining_usd, 2)
              : "暂无金额预估";
          return (
            <Tooltip
              key={id + key}
              title={
                <Box>
                  {buckets.length > 1 && <Box>{snapshot.limitName || id}</Box>}
                  <Box>{resetLabel(window?.resetsAt)}</Box>
                  <Box>{estimate}</Box>
                  <Box>
                    {amount?.reason ||
                      amount?.note ||
                      quota?.amount_estimate?.reason ||
                      "按本机用量与官方 API 价格折算，非订阅余额"}
                  </Box>
                </Box>
              }
            >
              <Box
                tabIndex={0}
                sx={{
                  display: "grid",
                  gridTemplateColumns: "18px minmax(0, 1fr) 27px",
                  alignItems: "center",
                  gap: 0.4,
                }}
              >
                <Typography
                  variant="caption"
                  color="textSecondary"
                  sx={{ fontSize: 10, lineHeight: 1.3 }}
                >
                  {label}
                </Typography>
                <LinearProgress
                  aria-label={label + "剩余"}
                  aria-valuetext={
                    known ? remaining.toFixed(0) + "%" : "配额未知"
                  }
                  variant="determinate"
                  value={remaining}
                  color={known && remaining < 20 ? "warning" : "primary"}
                  sx={{
                    height: 3,
                    bgcolor: "divider",
                    "& .MuiLinearProgress-bar": { borderRadius: 3 },
                  }}
                />
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: 10,
                    fontWeight: 600,
                    textAlign: "right",
                    lineHeight: 1.3,
                  }}
                >
                  {known ? remaining.toFixed(0) + "%" : "—"}
                </Typography>
              </Box>
            </Tooltip>
          );
        })
      )}
    </Stack>
  );
}

export default function AccountCard({
  account,
  quota,
  restartRequired,
  locked,
  api,
  onQuota,
  onDetails,
  onActivate,
}: Props) {
  const [loading, setLoading] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  const callback = useRef(onQuota);
  callback.current = onQuota;
  const official = account.account_type === "official";
  async function refresh() {
    if (!official || pending.current) return;
    pending.current = true;
    setLoading(true);
    let next: Quota;
    try {
      const response = await api<Quota>(
        `/api/accounts/quota?name=${encodeURIComponent(account.name)}`
      );
      if (!response.result) throw new Error("官方暂未返回额度数据");
      next = response.result;
    } catch (error) {
      next = { errors: { request: errorText(error) } };
    }
    if (mounted.current) {
      callback.current(next);
      setLoading(false);
    }
    pending.current = false;
  }
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
    };
  }, []);
  const actions = (
    <Stack
      direction="row"
      spacing={0.25}
      sx={{
        flexShrink: 0,
        alignItems: "center",
        "& .MuiButton-root": { minWidth: 0, px: 0.75 },
        "& .MuiIconButton-root": { p: 0.5 },
      }}
    >
      {official && (
        <Tooltip title="刷新额度">
          <span>
            <IconButton
              aria-label={"刷新" + account.name + "额度"}
              disabled={locked || loading}
              onClick={() => void refresh()}
            >
              {loading ? (
                <CircularProgress size={15} />
              ) : (
                <RefreshRounded fontSize="small" />
              )}
            </IconButton>
          </span>
        </Tooltip>
      )}
      <Button onClick={onDetails} disabled={locked}>
        详情
      </Button>
      <Button
        variant={
          account.active && !account.pending_apply ? "outlined" : "contained"
        }
        onClick={onActivate}
        disabled={locked || (account.active && !account.pending_apply)}
      >
        {account.active
          ? account.pending_apply
            ? "应用修改"
            : "使用中"
          : "使用"}
      </Button>
    </Stack>
  );
  return (
    <Box
      component="article"
      role="listitem"
      aria-label={account.name}
      sx={{
        px: 1.25,
        py: 1.25,
        minWidth: 0,
        minHeight: 64,
        border: "1px solid",
        borderColor: account.active ? "primary.light" : "transparent",
        borderRadius: "12px",
        bgcolor: "background.paper",
      }}
    >
      <Stack
        direction="row"
        spacing={1}
        sx={{
          alignItems: "center",
          flexWrap: "nowrap",
          gap: 0.75,
          minHeight: 42,
        }}
      >
        <Box
          sx={{
            width: 30,
            height: 30,
            display: "grid",
            placeItems: "center",
            bgcolor: "action.selected",
            color: "primary.main",
            borderRadius: "8px",
            flexShrink: 0,
          }}
        >
          {official ? (
            <PersonOutlineRounded fontSize="small" />
          ) : (
            <DnsOutlined fontSize="small" />
          )}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Typography
              variant="body2"
              noWrap
              title={account.name}
              sx={{ fontWeight: 650, minWidth: 0, fontSize: 12 }}
            >
              {account.name}
            </Typography>
          </Stack>
          {!official && (
            <Typography
              variant="caption"
              color="textSecondary"
              noWrap
              component="div"
              title={account.base_url}
            >
              {account.base_url || "未设置服务地址"}
            </Typography>
          )}
          {official && (
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Chip
                variant="outlined"
                color="primary"
                label={account.plan_type?.toUpperCase() || "OpenAI"}
                sx={{ height: 16, fontSize: 9 }}
              />
            </Stack>
          )}
        </Box>
        {official && <CompactQuota quota={quota} loading={loading} />}

        {actions}
      </Stack>
      {account.pending_apply && (
        <Typography
          variant="caption"
          color="warning.main"
          sx={{ display: "block", mt: 0.5 }}
        >
          待应用修改
        </Typography>
      )}
      {official && Object.keys(quota?.errors || {}).length > 0 && (
        <Typography
          role="status"
          variant="caption"
          color="error"
          sx={{ display: "block", mt: 0.75, overflowWrap: "anywhere" }}
        >
          额度读取失败：
          {[...new Set(Object.values(quota?.errors || {}))].join("；")}
        </Typography>
      )}
    </Box>
  );
}
