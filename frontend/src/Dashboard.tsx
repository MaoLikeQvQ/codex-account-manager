import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  InputAdornment,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import DownloadRounded from "@mui/icons-material/DownloadRounded";
import SearchRounded from "@mui/icons-material/SearchRounded";
import SyncRounded from "@mui/icons-material/SyncRounded";
import { localDate, money, tokens } from "./api";
import { TokenConsumption } from "./TokenConsumption";
import { mono, tpsColor } from "./theme";
import type { Account, RequestFeed, Usage } from "./types";

const cardStyle = {
  borderRadius: "12px",
  boxShadow: "0 3px 14px #20243404",
};
export const panelStyle = cardStyle;

export function Overview({
  usage,
  period,
  onDetails,
  feed,
}: {
  usage: Usage | null;
  period: string;
  onDetails: () => void;
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
  const periodLabel = (
    {
      today: "今日",
      yesterday: "昨日",
      "7d": "近 7 天",
      date: "所选日期",
    } as Record<string, string>
  )[period];
  return (
    <Paper
      aria-label="用量概览"
      sx={{
        ...cardStyle,
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
          label: `${periodLabel}估算费用`,
          value: (
            <>
              {totals?.unpriced_tokens ? "≥ " : ""}
              {money(totals?.estimated_cost)}
            </>
          ),
          help: (
            <Stack direction="row" sx={{ alignItems: "center", gap: 0.75 }}>
              <Tooltip title="按公开 API 标准价估算，不代表账单或订阅扣费">
                <Box component="span">API 等价 USD</Box>
              </Tooltip>
              <Button
                onClick={onDetails}
                sx={{
                  p: 0,
                  minWidth: 0,
                  minHeight: 0,
                  fontSize: "inherit",
                  lineHeight: "inherit",
                }}
              >
                明细
              </Button>
            </Stack>
          ),
        },
        {
          label: `${periodLabel}请求`,
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
          help: "请求平均速率，含等待",
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
          <Typography
            sx={{ display: "block" }}
            variant="caption"
            color="textSecondary"
          >
            {item.label}
          </Typography>
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
          <Typography
            component="div"
            variant="caption"
            color="textSecondary"
            sx={{ display: "block", lineHeight: 1.5 }}
          >
            {item.help}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}

export function UsagePanel({
  usage,
  error,
  loading,
  period,
  setPeriod,
  date,
  setDate,
  refresh,
  syncPrices,
  syncingPrices,
  active,
  onAccounts,
}: {
  usage: Usage | null;
  error: string;
  loading: boolean;
  period: string;
  setPeriod: (period: string) => void;
  date: string;
  setDate: (date: string) => void;
  refresh: () => void;
  syncPrices: () => void;
  syncingPrices: boolean;
  active?: Account;
  onAccounts: () => void;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(8);
  const rows = useMemo(
    () =>
      (usage?.models ?? []).filter((row) =>
        row.model.toLowerCase().includes(search.toLowerCase())
      ),
    [usage, search]
  );
  useEffect(() => setPage(0), [usage, search, rowsPerPage]);
  const totalTokens = usage
    ? usage.totals.input_tokens + usage.totals.output_tokens
    : 0;
  const exportCsv = () => {
    const csv = [
      "模型,输入Token,缓存输入Token,输出Token,思考Token,估算API费用USD",
      ...rows.map((row) =>
        [
          `"${row.model.replace(/"/g, '""')}"`,
          row.input_tokens,
          row.cached_input_tokens,
          row.output_tokens,
          row.reasoning_output_tokens,
          row.estimated_cost,
        ].join(",")
      ),
    ].join("\r\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" })
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `maox-usage-${usage?.date ?? localDate()}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        sx={{
          justifyContent: "space-between",
          px: 2,
          pt: 1.5,
          pb: 1.25,
          flexShrink: 0,
        }}
      >
        <Box>
          <Typography variant="subtitle2">模型用量明细</Typography>
          <Typography variant="caption" color="textSecondary">
            {usage
              ? `${usage.date}${
                  usage.end_date !== usage.date ? ` — ${usage.end_date}` : ""
                } · ${usage.provider_id} · ${tokens(totalTokens)} Token`
              : active
              ? "读取本机记录，按当前 Provider 汇总"
              : "添加并启用账号后，查看本机用量"}
          </Typography>
        </Box>
        <Stack
          sx={{ alignItems: "center", flexWrap: "wrap" }}
          direction="row"
          spacing={0.8}
          useFlexGap
        >
          <TextField
            select
            label="时间范围"
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
            sx={{ width: 110 }}
          >
            <MenuItem value="today">今天</MenuItem>
            <MenuItem value="yesterday">昨天</MenuItem>
            <MenuItem value="7d">近 7 天</MenuItem>
            <MenuItem value="date">指定日期</MenuItem>
          </TextField>
          {period === "date" && (
            <TextField
              label="日期"
              type="date"
              value={date}
              onChange={(event) => {
                if (event.target.value) setDate(event.target.value);
              }}
              slotProps={{
                inputLabel: { shrink: true },
                htmlInput: { max: localDate(), required: true },
              }}
              sx={{ width: 145 }}
            />
          )}
          <Tooltip title="刷新用量">
            <span>
              <IconButton
                aria-label="刷新用量"
                disabled={loading || !active}
                onClick={refresh}
              >
                <RefreshRounded fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Button
            variant="outlined"
            aria-label="同步模型价格"
            aria-busy={syncingPrices}
            startIcon={<SyncRounded fontSize="small" />}
            loading={syncingPrices}
            onClick={syncPrices}
          >
            同步模型价格
          </Button>
          <Button
            variant="outlined"
            startIcon={<DownloadRounded fontSize="small" />}
            onClick={exportCsv}
            disabled={!rows.length}
          >
            导出
          </Button>
        </Stack>
      </Stack>
      {error && (
        <Alert
          severity="error"
          sx={{ mx: 2, mb: 1.5 }}
          action={<Button onClick={refresh}>重试</Button>}
        >
          {error}
        </Alert>
      )}
      {usage?.skipped_files ? (
        <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
          有 {usage.skipped_files} 个文件未能读取，统计可能不完整。
        </Alert>
      ) : null}
      {usage?.totals.unpriced_tokens ? (
        <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
          {tokens(usage.totals.unpriced_tokens)} Token
          缺少价格，未计入估算费用。
        </Alert>
      ) : null}
      <Box sx={{ height: 3, flexShrink: 0 }}>
        {loading && <LinearProgress aria-label="正在读取用量" />}
      </Box>
      <TableContainer
        sx={{
          flex: "0 1 auto",
          minHeight: 60,
          maxHeight: 420,
        }}
      >
        <Table
          stickyHeader
          size="small"
          aria-label="模型用量明细"
          sx={{
            minWidth: 610,
            tableLayout: "fixed",
            "& .MuiTableCell-root": { px: 1 },
            "& th": { whiteSpace: "nowrap" },
          }}
        >
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: "24%" }}>模型 / 配置</TableCell>
              <TableCell align="right" sx={{ width: "20%" }}>
                估算费用 (USD)
              </TableCell>
              <TableCell align="right" sx={{ width: "23%" }}>
                Token 消耗
              </TableCell>
              <TableCell sx={{ width: "20%" }}>Token 占比</TableCell>
              <TableCell align="right" sx={{ width: "13%" }}>
                缓存率
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows
              .slice(page * rowsPerPage, (page + 1) * rowsPerPage)
              .map((row) => {
                const share = totalTokens
                  ? ((row.input_tokens + row.output_tokens) / totalTokens) * 100
                  : 0;
                const cache = row.input_tokens
                  ? (row.cached_input_tokens / row.input_tokens) * 100
                  : null;
                return (
                  <TableRow key={row.model} hover>
                    <TableCell>
                      <Typography
                        sx={{
                          fontFamily: mono,
                          fontWeight: 650,
                          fontSize: 12,
                          overflowWrap: "anywhere",
                        }}
                      >
                        {row.model}
                      </Typography>
                      <Chip
                        label="Standard 估价"
                        sx={{
                          height: 18,
                          mt: 0.5,
                          fontSize: 9,
                          color: "text.secondary",
                          bgcolor: "action.hover",
                        }}
                      />
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ fontFamily: mono, fontWeight: 600 }}
                    >
                      {row.unpriced_tokens ? "≥ " : ""}
                      {money(row.estimated_cost, 6)}
                    </TableCell>
                    <TableCell align="right">
                      <TokenConsumption {...row} />
                    </TableCell>
                    <TableCell sx={{ width: "19%" }}>
                      <Stack
                        sx={{ alignItems: "center" }}
                        direction="row"
                        spacing={1}
                      >
                        <LinearProgress
                          aria-label={`${row.model} Token 占比`}
                          variant="determinate"
                          value={Math.min(100, share)}
                          sx={{ flex: 1 }}
                        />
                        <Typography
                          variant="caption"
                          sx={{ fontFamily: mono, minWidth: 42 }}
                          color="textSecondary"
                        >
                          {share.toFixed(1)}%
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        fontFamily: mono,
                        fontWeight: 650,
                        color: "success.main",
                      }}
                    >
                      {cache == null ? "—" : `${cache.toFixed(1)}%`}
                    </TableCell>
                  </TableRow>
                );
              })}
            {!rows.length && (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 7 }}>
                  <Typography color="textSecondary">
                    {loading
                      ? "正在读取用量…"
                      : !active
                      ? "还没有启用账号"
                      : search
                      ? "没有匹配的模型"
                      : "所选时间暂无用量记录"}
                  </Typography>
                  {!active && (
                    <Button onClick={onAccounts} sx={{ mt: 1 }}>
                      前往账号管理
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        sx={{
          justifyContent: "space-between",
          alignItems: { xs: "stretch", sm: "center" },
          px: 2,
          flexShrink: 0,
        }}
      >
        <TextField
          placeholder="筛选模型"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          slotProps={{
            htmlInput: { "aria-label": "筛选模型" },
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchRounded sx={{ fontSize: 16 }} />
                </InputAdornment>
              ),
            },
          }}
          sx={{
            width: 190,
            my: 0.75,
            "& fieldset": { border: 0 },
            "& .MuiInputBase-root": { bgcolor: "action.hover" },
            "& input": { py: 0.8, fontSize: 12 },
          }}
        />
        <TablePagination
          component="div"
          count={rows.length}
          page={Math.min(
            page,
            Math.max(0, Math.ceil(rows.length / rowsPerPage) - 1)
          )}
          rowsPerPage={rowsPerPage}
          onPageChange={(_, next) => setPage(next)}
          onRowsPerPageChange={(event) =>
            setRowsPerPage(Number(event.target.value))
          }
          rowsPerPageOptions={[8, 15, 30]}
          labelRowsPerPage="每页"
          labelDisplayedRows={({ from, to, count }) =>
            `${from}–${to} / ${count} 个模型`
          }
          getItemAriaLabel={(type) => (type === "next" ? "下一页" : "上一页")}
          sx={{
            border: 0,
            "& .MuiTablePagination-toolbar": { minHeight: 40, pl: 0 },
            "& .MuiTablePagination-selectLabel, & .MuiTablePagination-displayedRows":
              { fontSize: 11, color: "text.secondary" },
          }}
        />
      </Stack>
      <Box
        sx={{
          px: 2,
          py: 1,
          flexShrink: 0,
          borderTop: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography variant="caption" color="textSecondary">
          按 Provider 汇总本机记录，同 Provider
          下多个账号合并统计。思考已包含在输出中。估算费用不代表渠道账单或订阅扣费。
          {usage?.pricing?.warning && ` ${usage.pricing.warning} `}
          {usage?.pricing?.updated_at && (
            <>
              {" "}
              最近同步于{" "}
              {new Date(usage.pricing.updated_at * 1000).toLocaleString(
                "zh-CN",
                { hour12: false }
              )}
              。
            </>
          )}
          <Link
            href={
              usage?.price_source ||
              "https://developers.openai.com/api/docs/pricing"
            }
            target="_blank"
            rel="noopener noreferrer"
            sx={{ ml: 0.8 }}
          >
            价格来源 ↗
          </Link>
        </Typography>
      </Box>
    </>
  );
}
