import type { ReactNode } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import AutoAwesomeOutlined from "@mui/icons-material/AutoAwesomeOutlined";
import TollOutlined from "@mui/icons-material/TollOutlined";
import NearMeOutlined from "@mui/icons-material/NearMeOutlined";
import BarChartRounded from "@mui/icons-material/BarChartRounded";
import LayersOutlined from "@mui/icons-material/LayersOutlined";
import ArrowForwardRounded from "@mui/icons-material/ArrowForwardRounded";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import { money, tokens } from "./api";
import { panelStyle } from "./Dashboard";
import type {
  Account,
  AppState,
  Quota,
  QuotaSnapshot,
  RequestFeed,
  Usage,
} from "./types";

interface Props {
  active?: Account;
  state: AppState | null;
  quota?: Quota;
  quotaLoading: boolean;
  refreshQuota: () => void;
  usage: Usage | null;
  feed: RequestFeed | null;
  usageError: string;
  requestError: string;
  period: string;
  onNavigate: (tab: number) => void;
}

function resetTime(timestamp?: number) {
  if (!timestamp || !Number.isFinite(timestamp)) return "";
  const minutes = Math.ceil((timestamp * 1000 - Date.now()) / 60000);
  if (minutes <= 0) return "等待重置";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return (
    (days ? days + " 天 " : "") +
    (hours ? hours + " 小时" : days ? "" : minutes + " 分钟") +
    "后重置"
  );
}

function QuotaBars({ quota, loading }: { quota?: Quota; loading: boolean }) {
  const limits = quota?.limits;
  const buckets: [string, QuotaSnapshot][] =
    limits?.rateLimitsByLimitId &&
    Object.keys(limits.rateLimitsByLimitId).length
      ? Object.entries(limits.rateLimitsByLimitId)
      : limits?.rateLimits
      ? [["Codex", limits.rateLimits]]
      : [];
  const windows = (
    buckets.length ? buckets : [["Codex", {}] as [string, QuotaSnapshot]]
  ).flatMap(([id, snapshot]) =>
    (["primary", "secondary"] as const).map((key) => {
      const window = snapshot[key];
      const known =
        typeof window?.usedPercent === "number" &&
        Number.isFinite(window.usedPercent);
      const remaining = known
        ? 100 - Math.max(0, Math.min(100, window.usedPercent!))
        : null;
      const duration = window?.windowDurationMins;
      const label =
        duration === 300
          ? "5 小时"
          : duration === 10080
          ? "每周"
          : duration
          ? duration + " 分钟"
          : key === "primary"
          ? "短周期"
          : "长周期";
      return {
        id: id + key,
        label: (snapshot.limitName || id) + " · " + label,
        remaining,
        reset: resetTime(window?.resetsAt),
      };
    })
  );
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
        gap: 2,
        py: 1,
      }}
    >
      {windows.map((window) => (
        <Box key={window.id}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", mb: 0.5 }}
          >
            <Typography variant="caption" sx={{ flex: 1 }}>
              {window.label}
            </Typography>
            <Typography
              variant="caption"
              color="textSecondary"
              sx={{ display: { xs: "none", md: "block" } }}
            >
              {window.reset}
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 650 }}>
              {window.remaining == null
                ? loading
                  ? "读取中…"
                  : "—"
                : window.remaining.toFixed(0) + "%"}
            </Typography>
          </Stack>
          <LinearProgress
            aria-label={window.label + "剩余配额"}
            aria-valuetext={
              window.remaining == null
                ? "配额未知"
                : window.remaining.toFixed(0) + "%"
            }
            variant="determinate"
            value={window.remaining ?? 0}
            color={
              window.remaining != null && window.remaining < 20
                ? "warning"
                : "primary"
            }
            sx={{
              height: 7,
              "& .MuiLinearProgress-bar": {
                borderRadius: 8,
                backgroundImage:
                  window.remaining == null || window.remaining < 20
                    ? "none"
                    : "linear-gradient(90deg, #6596f4, #0866ed)",
              },
            }}
          />
        </Box>
      ))}
    </Box>
  );
}

function CardHeading({
  icon,
  title,
  action,
}: {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
}) {
  return (
    <Stack direction="row" spacing={0.8} sx={{ alignItems: "center", mb: 1 }}>
      <Box
        sx={{
          width: 24,
          height: 24,
          borderRadius: "6px",
          bgcolor: "action.selected",
          color: "primary.main",
          display: "grid",
          placeItems: "center",
          "& svg": { fontSize: 17 },
        }}
      >
        {icon}
      </Box>
      <Typography component="h2" variant="subtitle2" sx={{ flex: 1 }}>
        {title}
      </Typography>
      {action}
    </Stack>
  );
}

export default function OverviewPage({
  active,
  state,
  quota,
  quotaLoading,
  refreshQuota,
  usage,
  feed,
  usageError,
  requestError,
  period,
  onNavigate,
}: Props) {
  const periodLabel =
    (
      {
        today: "今日",
        yesterday: "昨日",
        "7d": "近 7 天",
        date: "所选日期",
      } as Record<string, string>
    )[period] || "所选范围";
  const totals = usage?.totals;
  const totalTokens = totals
    ? totals.input_tokens + totals.output_tokens
    : null;
  const modelRows = [...(usage?.models || [])].sort(
    (a, b) =>
      b.input_tokens + b.output_tokens - (a.input_tokens + a.output_tokens)
  );
  // The feed contains a limited set of recent responses, so label this sample explicitly.
  const hours = Array.from({ length: 24 }, () => 0);
  for (const row of feed?.requests || []) {
    const timestamp = new Date(row.timestamp);
    if (Number.isFinite(timestamp.getTime()))
      hours[timestamp.getHours()] += row.input_tokens + row.output_tokens;
  }
  const maxHour = Math.max(...hours, 1);
  const sampleTokens = hours.reduce((sum, value) => sum + value, 0);
  const official = active?.account_type === "official";
  const quotaErrors = [...new Set(Object.values(quota?.errors || {}))];
  return (
    <Stack spacing={1} sx={{ pb: 0.5 }}>
      <Paper
        component="section"
        aria-label="当前账号"
        sx={{ ...panelStyle, px: 1.75, py: 1.25 }}
      >
        {active ? (
          <>
            <Stack
              direction="row"
              spacing={1}
              sx={{ alignItems: "center", mb: official ? 1 : 0 }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack
                  direction="row"
                  spacing={0.8}
                  sx={{ alignItems: "center" }}
                >
                  <Typography variant="h6" noWrap title={active.name}>
                    {active.name}
                  </Typography>
                  <Chip
                    variant="outlined"
                    label={
                      official
                        ? active.plan_type?.toUpperCase() || "OPENAI"
                        : active.connection_type === "sub2api"
                        ? "SUB2API"
                        : "API"
                    }
                    sx={{
                      height: 19,
                      fontSize: 9,
                      bgcolor: "action.hover",
                      color: "text.secondary",
                      letterSpacing: ".6px",
                    }}
                  />
                  {active.pending_apply && (
                    <Chip color="warning" label="待应用" />
                  )}
                </Stack>
                <Typography
                  variant="caption"
                  color="textSecondary"
                  noWrap
                  component="div"
                  sx={{ mt: 0.25 }}
                >
                  {active.email || active.base_url || "OpenAI 官方账号"}
                </Typography>
              </Box>
              {official ? (
                <Button
                  variant="outlined"
                  disabled={quotaLoading}
                  onClick={refreshQuota}
                  startIcon={
                    quotaLoading ? (
                      <CircularProgress size={13} />
                    ) : (
                      <RefreshRounded sx={{ fontSize: 15 }} />
                    )
                  }
                >
                  刷新配额
                </Button>
              ) : (
                <Button variant="outlined" onClick={() => onNavigate(1)}>
                  管理账号
                </Button>
              )}
            </Stack>
            {official && <Divider />}
            {official ? (
              <QuotaBars quota={quota} loading={quotaLoading} />
            ) : (
              <Stack
                direction="row"
                spacing={1}
                useFlexGap
                sx={{
                  flexWrap: "wrap",
                  mt: 0.5,
                  alignItems: "center",
                  color: "text.secondary",
                }}
              >
                <Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>
                  当前模型 · {state?.current.model || "未设置"}
                </Typography>
                <Typography variant="caption">
                  {active.transport === "websocket"
                    ? "WebSocket"
                    : "HTTP / SSE"}
                </Typography>
              </Stack>
            )}
            {official && quota?.fetched_at && (
              <Typography variant="caption" color="textSecondary">
                配额更新于 {new Date(quota.fetched_at).toLocaleString("zh-CN")}
              </Typography>
            )}
            {quotaErrors.map((error) => (
              <Alert key={error} severity="error" sx={{ mt: 1 }}>
                配额读取失败：{error}
              </Alert>
            ))}
            {official && quota?.limits?.ordinaryUsageAllowed === false && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                官方当前不允许使用套餐内额度。
              </Alert>
            )}
            {official &&
              !quotaLoading &&
              !quota?.limits &&
              !quotaErrors.length && (
                <Typography variant="caption" color="textSecondary">
                  暂无配额数据，可点击“刷新配额”重试。
                </Typography>
              )}
          </>
        ) : (
          <Stack sx={{ alignItems: "flex-start", py: 1 }} spacing={1}>
            <Typography variant="h6">连接你的 Codex 账号</Typography>
            <Typography variant="body2" color="textSecondary">
              添加官方账号或兼容渠道，开始查看配额与本机用量。
            </Typography>
            <Button variant="contained" onClick={() => onNavigate(1)}>
              前往账号管理
            </Button>
          </Stack>
        )}
      </Paper>
      {(usageError || requestError) && (
        <Alert severity="error">
          {[...new Set([usageError, requestError].filter(Boolean))].join("；")}
        </Alert>
      )}
      <Box
        aria-label="用量概览"
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" },
          gap: 1.25,
        }}
      >
        {[
          {
            label: periodLabel + " Token 用量",
            icon: <AutoAwesomeOutlined />,
            color: "#3176ed",
            bg: "#edf3ff",
            value: totalTokens == null ? "—" : tokens(totalTokens),
            help:
              quota?.usage?.summary?.lifetimeTokens != null
                ? "账号累计 " +
                  tokens(quota.usage.summary.lifetimeTokens) +
                  " Token"
                : "输入 " +
                  tokens(totals?.input_tokens) +
                  " · 输出 " +
                  tokens(totals?.output_tokens),
          },
          {
            label: periodLabel + "估算费用",
            icon: <TollOutlined />,
            color: "#00a9bd",
            bg: "#e9f8fa",
            value: totals
              ? (totals.unpriced_tokens ? "≥ " : "") +
                money(totals.estimated_cost)
              : "—",
            help: "API 等价 USD",
          },
          {
            label: periodLabel + "请求次数",
            icon: <NearMeOutlined />,
            color: "#7765e8",
            bg: "#f0edff",
            value: feed ? feed.total_requests.toLocaleString() : "—",
            help: "按单次模型响应计数",
          },
        ].map((item) => (
          <Paper key={item.label} sx={{ ...panelStyle, p: 1.25, minWidth: 0 }}>
            <Stack
              direction="row"
              spacing={0.8}
              sx={{ alignItems: "center", mb: 0.5 }}
            >
              <Box
                sx={{
                  width: 23,
                  height: 23,
                  borderRadius: "6px",
                  bgcolor: item.bg,
                  color: item.color,
                  display: "grid",
                  placeItems: "center",
                  "& svg": { fontSize: 16 },
                }}
              >
                {item.icon}
              </Box>
              <Typography
                variant="caption"
                color="textSecondary"
                sx={{ fontWeight: 600 }}
              >
                {item.label}
              </Typography>
            </Stack>
            <Typography
              sx={{
                fontSize: 25,
                letterSpacing: "-.8px",
                fontWeight: 700,
                lineHeight: 1.3,
              }}
            >
              {item.value}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {item.help}
            </Typography>
          </Paper>
        ))}
      </Box>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          alignItems: "start",
          gap: 1.25,
        }}
      >
        <Paper
          component="section"
          aria-label="请求时段分布"
          sx={{ ...panelStyle, p: 1.25, minWidth: 0 }}
        >
          <CardHeading
            icon={<BarChartRounded />}
            title="请求时段分布"
            action={
              <Chip
                label="24 小时分布"
                variant="outlined"
                sx={{
                  color: "primary.main",
                  bgcolor: "action.hover",
                  height: 20,
                }}
              />
            }
          />
          <Divider />
          <Typography
            variant="caption"
            color="textSecondary"
            component="div"
            sx={{ mt: 1 }}
          >
            {periodLabel} · 最近 {feed?.requests.length ?? 0} 次响应 ·{" "}
            {tokens(sampleTokens)} Token
          </Typography>
          {feed?.requests.length ? (
            <>
              <Box
                role="img"
                aria-label="最近响应在各小时的 Token 分布"
                sx={{
                  height: 90,
                  display: "flex",
                  alignItems: "flex-end",
                  gap: { xs: "3px", lg: "5px" },
                  pt: 1.5,
                  pb: 0.5,
                  borderBottom: "1px solid",
                  borderColor: "divider",
                }}
              >
                {hours.map((value, hour) => (
                  <Tooltip
                    key={hour}
                    title={hour + ":00 · " + value.toLocaleString() + " Token"}
                  >
                    <Box
                      tabIndex={value ? 0 : undefined}
                      aria-label={
                        hour + " 时 " + value.toLocaleString() + " Token"
                      }
                      sx={{
                        flex: 1,
                        minWidth: 0,
                        height: value
                          ? Math.max(5, (value / maxHour) * 100) + "%"
                          : 3,
                        bgcolor: value ? "primary.main" : "action.selected",
                        opacity: value ? 0.8 : 1,
                        borderRadius: "3px 3px 0 0",
                        "&:hover, &:focus-visible": { opacity: 1 },
                      }}
                    />
                  </Tooltip>
                ))}
              </Box>
              <Stack
                direction="row"
                sx={{ justifyContent: "space-between", pt: 0.75 }}
              >
                <Typography variant="caption" color="textSecondary">
                  00:00
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  12:00
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  23:00
                </Typography>
              </Stack>
            </>
          ) : (
            <Box sx={{ minHeight: 125, display: "grid", placeItems: "center" }}>
              <Typography variant="caption" color="textSecondary">
                {requestError
                  ? "请求记录读取失败"
                  : feed
                  ? "当前时段暂无消耗分布"
                  : active
                  ? "正在读取请求记录…"
                  : "启用账号后查看时段分布"}
              </Typography>
            </Box>
          )}
          <Button
            endIcon={<ArrowForwardRounded />}
            onClick={() => onNavigate(3)}
            sx={{ mt: 0.75, p: 0, minHeight: 24, fontSize: 11 }}
          >
            查看请求记录
          </Button>
        </Paper>
        <Paper
          component="section"
          aria-label="活跃模型"
          sx={{ ...panelStyle, p: 1.25, minWidth: 0 }}
        >
          <CardHeading
            icon={<LayersOutlined />}
            title={periodLabel + "活跃模型"}
            action={
              <Chip
                label={usage ? modelRows.length + " 个模型" : "—"}
                variant="outlined"
                sx={{
                  color: "primary.main",
                  bgcolor: "action.hover",
                  height: 20,
                }}
              />
            }
          />
          <Divider />
          <Stack spacing={1} sx={{ mt: 1, minHeight: 0 }}>
            {modelRows.slice(0, 3).map((row) => (
              <Box
                key={row.model}
                sx={{ bgcolor: "action.hover", p: 1, borderRadius: "10px" }}
              >
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ justifyContent: "space-between", mb: 0.5 }}
                >
                  <Typography
                    variant="body2"
                    noWrap
                    title={row.model}
                    sx={{ fontWeight: 600, minWidth: 0 }}
                  >
                    {row.model}
                  </Typography>
                  <Typography variant="caption" color="textSecondary" noWrap>
                    {tokens(row.input_tokens + row.output_tokens)} Token
                  </Typography>
                </Stack>
                <LinearProgress
                  aria-label={row.model + " 用量占比"}
                  variant="determinate"
                  value={
                    totalTokens
                      ? Math.min(
                          100,
                          ((row.input_tokens + row.output_tokens) /
                            totalTokens) *
                            100
                        )
                      : 0
                  }
                  sx={{ height: 4 }}
                />
              </Box>
            ))}
            {!modelRows.length && (
              <Box
                sx={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  alignItems: "center",
                  py: 2.5,
                }}
              >
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  {usageError
                    ? "模型用量读取失败"
                    : usage
                    ? "暂无模型调用"
                    : active
                    ? "正在读取模型用量…"
                    : "尚未启用账号"}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  在 Codex 发起请求后，将在此显示。
                </Typography>
              </Box>
            )}
          </Stack>
          <Button
            endIcon={<ArrowForwardRounded />}
            onClick={() => onNavigate(0)}
            sx={{ mt: 0.75, p: 0, minHeight: 24, fontSize: 11 }}
          >
            查看完整用量
          </Button>
        </Paper>
      </Box>
      <Typography variant="caption" color="textSecondary" sx={{ px: 0.5 }}>
        用量来自本机 Codex 记录；费用按公开 API
        标准价估算，不代表服务商账单或订阅扣费。
        {totals?.unpriced_tokens ? " 部分 Token 缺少价格，暂未计入费用。" : ""}
      </Typography>
    </Stack>
  );
}
