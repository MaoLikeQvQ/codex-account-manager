import { Alert, Box, LinearProgress, Stack, Typography } from "@mui/material";
import { money, tokens } from "./api";
import type { Account, Quota, QuotaSnapshot } from "./types";

export default function AccountQuota({
  account,
  quota,
}: {
  account: Account;
  quota?: Quota;
}) {
  if (!quota)
    return (
      <Typography variant="body2" color="textSecondary">
        读取官方的短周期、每周额度和累计 Token，无需切换账号。
      </Typography>
    );
  const limits = quota.limits;
  const buckets: [string, QuotaSnapshot][] =
    limits?.rateLimitsByLimitId &&
    Object.keys(limits.rateLimitsByLimitId).length
      ? Object.entries(limits.rateLimitsByLimitId)
      : limits
        ? [["Codex", limits.rateLimits || {}]]
        : [];
  return (
    <Stack spacing={1.5}>
      {buckets.map(([id, snapshot]) => (
        <Box key={id}>
          <Stack
            direction="row"
            sx={{ justifyContent: "space-between", mb: 1 }}
          >
            <Typography sx={{ fontWeight: 600 }} variant="body2">
              {snapshot.limitName || id}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {snapshot.planType || account.plan_type}
            </Typography>
          </Stack>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              gap: 1.5,
            }}
          >
            {(["primary", "secondary"] as const).map((key) => {
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
                  ? "5 小时额度"
                  : duration === 10080
                    ? "每周额度"
                    : duration
                      ? `${duration} 分钟额度`
                      : key === "primary"
                        ? "短周期额度"
                        : "长周期额度";
              const amount = quota.amount_estimate?.windows?.[`${id}:${key}`];
              return (
                <Box
                  key={key}
                  sx={{
                    p: 1.5,
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1.5,
                  }}
                >
                  <Typography variant="caption" color="textSecondary">
                    {label}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: "monospace",
                      fontSize: 24,
                      fontWeight: 650,
                      mt: 0.4,
                    }}
                  >
                    {known ? `${remaining.toFixed(0)}%` : "—"}
                    <Typography
                      component="span"
                      variant="caption"
                      color="textSecondary"
                    >
                      {" "}
                      剩余
                    </Typography>
                  </Typography>
                  {known && (
                    <LinearProgress
                      variant="determinate"
                      value={remaining}
                      color={remaining < 20 ? "warning" : "success"}
                      sx={{ mt: 1, mb: 1.5, height: 5, borderRadius: 1 }}
                    />
                  )}
                  {typeof amount?.remaining_usd === "number" &&
                  Number.isFinite(amount.remaining_usd) ? (
                    <>
                      <Typography variant="caption" sx={{ display: "block" }}>
                        API 等价估算 ≈ {money(amount.remaining_usd, 2)}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="textSecondary"
                        sx={{ display: "block" }}
                      >
                        周期 ≈ {money(amount.total_usd, 2)} · 已用 ≈{" "}
                        {money(amount.sample_usd, 2)}
                      </Typography>
                      {amount.note && (
                        <Typography
                          variant="caption"
                          color="textSecondary"
                          sx={{ display: "block" }}
                        >
                          {amount.note}
                        </Typography>
                      )}
                    </>
                  ) : (
                    <Typography
                      variant="caption"
                      color="textSecondary"
                      sx={{ display: "block" }}
                    >
                      {amount?.reason ||
                        quota.amount_estimate?.reason ||
                        "暂无可用金额估算"}
                    </Typography>
                  )}
                  <Typography
                    variant="caption"
                    color="textSecondary"
                    sx={{ display: "block", mt: 1 }}
                  >
                    {window?.resetsAt
                      ? `${new Date(window.resetsAt * 1000).toLocaleString()} 重置`
                      : "未提供重置时间"}
                  </Typography>
                </Box>
              );
            })}
          </Box>
          {snapshot.credits && (
            <Typography
              variant="caption"
              color="textSecondary"
              component="p"
              sx={{ mt: 1 }}
            >
              额外 credits：
              {snapshot.credits.unlimited
                ? "不限额"
                : (snapshot.credits.balance ??
                  (snapshot.credits.hasCredits
                    ? "有余额，未提供数值"
                    : "无可用 credits"))}
            </Typography>
          )}
        </Box>
      ))}
      {quota.usage && (
        <Box sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1.5 }}>
          <Typography variant="caption" color="textSecondary">
            账号累计 Token
          </Typography>
          <Typography
            sx={{ fontFamily: "monospace", fontSize: 23, fontWeight: 600 }}
          >
            {tokens(quota.usage.summary?.lifetimeTokens)}
          </Typography>
        </Box>
      )}
      {limits && (
        <Typography variant="caption" color="textSecondary">
          金额按本机记录、官方 API Standard
          价格与已用比例折算，不是订阅余额。跨设备使用、历史账号、模型与速度档位变化会影响估算。
        </Typography>
      )}
      {limits?.ordinaryUsageAllowed === false && (
        <Alert severity="warning">官方当前不允许使用套餐内额度。</Alert>
      )}
      {[...new Set(Object.values(quota.errors || {}))].map((error) => (
        <Alert severity="error" key={error}>
          {error}
        </Alert>
      ))}
      {!limits && !quota.usage && !Object.keys(quota.errors || {}).length && (
        <Alert severity="info">官方暂未返回额度数据，请稍后重试。</Alert>
      )}
      {quota.fetched_at && (
        <Typography variant="caption" color="textSecondary">
          更新于 {new Date(quota.fetched_at).toLocaleString()}
        </Typography>
      )}
    </Stack>
  );
}
