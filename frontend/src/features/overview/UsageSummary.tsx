import { Box, Paper, Tooltip, Typography } from "@mui/material";
import { money, tokens } from "../../shared/lib/format";
import { mono, tpsColor } from "../../shared/theme";
import type { RequestFeed, Usage } from "../../shared/types";
import { panelStyle } from "../../shared/ui/panelStyles";

export function UsageSummary({
  usage,
  feed,
}: {
  usage: Usage | null;
  feed: RequestFeed | null;
}) {
  const totals = usage?.totals;
  const latest = feed?.requests[0];
  const latestTps =
    latest &&
    latest.timing_source === "request_events" &&
    latest.tps != null &&
    Number.isFinite(latest.tps)
      ? latest.tps
      : null;
  const hitRate =
    totals && totals.input_tokens
      ? (totals.cached_input_tokens / totals.input_tokens) * 100
      : null;
  return (
    <Paper
      aria-label="用量概览"
      sx={{
        ...panelStyle,
        px: 0.5,
        py: 1,
        flexShrink: 0,
        display: "grid",
        gridTemplateColumns: {
          xs: "repeat(2, minmax(0, 1fr))",
          sm: "repeat(5, minmax(0, 1fr))",
        },
        rowGap: 1.5,
      }}
    >
      {[
        {
          label: "估算费用（USD）",
          value: (
            <>
              {totals?.unpriced_tokens ? "≥ " : ""}
              {money(totals?.estimated_cost)}
            </>
          ),
          help: "按公开 API 标准价估算，不代表实际账单或订阅扣费",
        },
        {
          label: "请求数",
          value: feed ? feed.total_requests.toLocaleString() : "—",
          help: "按单次模型响应计数",
        },
        {
          label: "缓存命中率",
          value: hitRate == null ? "—" : `${hitRate.toFixed(1)}%`,
          help: `复用 ${tokens(totals?.cached_input_tokens)} Token`,
          green: true,
        },
        {
          label: "最近请求 TPS",
          value:
            latestTps != null ? (
              <>
                {latestTps.toFixed(1)}{" "}
                <Box component="span" sx={{ color: "text.secondary" }}>
                  tok/s
                </Box>
              </>
            ) : (
              "—"
            ),
          color: tpsColor(latestTps),
          help: "所选范围内最近一条请求的平均输出速率，含等待；未采集计时则显示 —",
        },
        {
          label: "输出 Token",
          value: tokens(totals?.output_tokens),
          help: `其中思考 ${tokens(totals?.reasoning_output_tokens)}`,
        },
      ].map((item, index) => (
        <Box
          key={item.label}
          sx={{
            px: 1.4,
            py: { xs: 0.4, sm: 0 },
            borderLeftWidth: { xs: index % 2 ? 1 : 0, sm: index ? 1 : 0 },
            borderLeftStyle: "solid",
            borderColor: "divider",
          }}
        >
          <Tooltip title={item.help}>
            <Typography
              component="span"
              sx={{ display: "block", width: "fit-content" }}
              variant="caption"
              color="textSecondary"
              tabIndex={0}
            >
              {item.label}
            </Typography>
          </Tooltip>
          <Typography
            sx={{
              fontFamily: mono,
              fontSize: 20,
              fontWeight: 650,
              color:
                item.color || (item.green ? "success.main" : "text.primary"),
              lineHeight: 1.2,
            }}
          >
            {item.value}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
