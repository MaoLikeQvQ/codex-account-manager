import NetworkEvents from "./NetworkEvents";
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  LinearProgress,
  MenuItem,
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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import DownloadRounded from "@mui/icons-material/DownloadRounded";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import { localDate, money, tokens } from "./api";
import { TokenConsumption } from "./TokenConsumption";
import { elapsedTimeColor, mono, tpsColor } from "./theme";
import type { Account, RequestFeed, RequestRow } from "./types";

interface Props {
  feed: RequestFeed | null;
  loading: boolean;
  error: string;
  refresh: () => void;
  period: string;
  setPeriod: (value: string) => void;
  date: string;
  setDate: (value: string) => void;
  active?: Account;
}

const timingDescription =
  "使用本机 Codex 逐请求事件：首响为请求发起至收到 HTTP 响应头（SSE 连接响应），正文首字另计，总耗时为请求发起至响应完成；TPS 为输出 Token（含思考）除以总耗时。不再使用轮次耗时推算单次请求；未采集的旧记录显示未采集。并非流式生成速度；事件批量导出可能稍有延迟。";

function elapsed(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) || value < 0
    ? "—"
    : `${value.toFixed(2)}s`;
}

function observedTps(row: RequestRow) {
  return row.timing_source === "request_events" &&
    row.tps != null &&
    Number.isFinite(row.tps)
    ? row.tps
    : null;
}

function clockTime(timestamp: string) {
  const date = new Date(timestamp);
  return Number.isFinite(date.getTime())
    ? {
        day: date.toLocaleDateString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
        }),
        time: date.toLocaleTimeString("en-GB", { hour12: false }),
      }
    : { day: "—", time: "—" };
}

function exportRequests(feed: RequestFeed) {
  // CSV quoting also neutralizes spreadsheet formulas in model and session identifiers.
  const cell = (value: string | number | null | undefined) => {
    let text = value == null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const columns = [
    "时间",
    "Provider",
    "模型",
    "推理强度",
    "估算费用 USD",
    "估算 TPS (tok/s)",
    "请求总耗时 s",
    "输入 Token",
    "缓存输入 Token",
    "缓存写入 Token",
    "输出 Token（含思考）",
    "其中思考 Token",
    "会话 ID",
    "时间依据",
    "请求发起时间",
    "正文首字耗时 s",
    "连接首响耗时 s",
  ];
  const rows = feed.requests.map((row) => [
    row.timestamp,
    feed.provider_id,
    row.model,
    row.reasoning_effort,
    row.estimated_cost,
    observedTps(row),
    row.duration_seconds,
    row.input_tokens,
    row.cached_input_tokens,
    row.cache_write_input_tokens,
    row.output_tokens,
    row.reasoning_output_tokens,
    row.session_id,
    row.timing_source,
    row.request_started_at,
    row.first_token_seconds,
    row.first_response_seconds,
  ]);
  const csv = `\uFEFF${[columns, ...rows]
    .map((row) => row.map(cell).join(","))
    .join("\r\n")}`;
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8;" })
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `maox-requests-${feed.date}.csv`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function RequestsPanel({
  feed,
  loading,
  error,
  refresh,
  period,
  setPeriod,
  date,
  setDate,
  active,
}: Props) {
  const [view, setView] = useState("usage");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(15);
  const requests = feed?.requests ?? [];
  const count = requests.length;
  const safePage = Math.min(
    page,
    Math.max(0, Math.ceil(count / rowsPerPage) - 1)
  );
  const start = safePage * rowsPerPage;
  const dates = feed
    ? feed.date === feed.end_date
      ? feed.date
      : `${feed.date} — ${feed.end_date}`
    : period === "date"
    ? date
    : "本机用量记录";

  useEffect(() => {
    setPage(0);
  }, [period, date, active?.name, rowsPerPage]);

  return (
    <>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        sx={{
          px: 2,
          py: 1.25,
          justifyContent: "space-between",
          alignItems: { sm: "center" },
          flexShrink: 0,
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" color="textSecondary">
            {feed?.timing_coverage && (
              <Tooltip
                title={
                  feed.timing_coverage.desktop_total > 0 &&
                  feed.timing_coverage.desktop_timed === 0
                    ? "桌面请求尚缺少可关联的请求事件。完整退出并重新打开承载 Codex 的应用后，新请求才开始采集；CLI 计时不会计作桌面计时。"
                    : "仅统计已关联的请求计时，批量导出会有延迟。"
                }
              >
                <Box component="span" role="alert" sx={{ mr: 1 }}>
                  当前范围请求计时覆盖：{feed.timing_coverage.timed} /{" "}
                  {feed.timing_coverage.total}； 桌面{" "}
                  {feed.timing_coverage.desktop_timed} /{" "}
                  {feed.timing_coverage.desktop_total}； CLI{" "}
                  {feed.timing_coverage.cli_timed} ⓘ
                </Box>
              </Tooltip>
            )}
            {dates} · {feed?.provider_id || active?.provider_id || "未启用账号"}{" "}
            · {feed?.total_requests ?? 0} 次记录
            {feed && feed.total_requests > count
              ? ` · 展示最新 ${count} 次`
              : ""}
          </Typography>
        </Box>
        <Stack
          direction="row"
          spacing={0.8}
          sx={{
            alignItems: "center",
            flexWrap: "wrap",
            rowGap: 0.8,
            flexShrink: 0,
          }}
        >
          <TextField
            select
            value={period}
            onChange={(event) => {
              const selected = event.target.value;
              if (selected === "date" && !date) setDate(localDate());
              setPeriod(selected);
            }}
            sx={{ width: 108, "& .MuiInputBase-root": { fontSize: 12 } }}
            slotProps={{
              select: { SelectDisplayProps: { "aria-label": "请求时间范围" } },
            }}
          >
            <MenuItem value="today">今天</MenuItem>
            <MenuItem value="yesterday">昨天</MenuItem>
            <MenuItem value="7d">近 7 天</MenuItem>
            <MenuItem value="date">指定日期</MenuItem>
          </TextField>
          {period === "date" && (
            <TextField
              type="date"
              value={date || localDate()}
              onChange={(event) => {
                if (event.target.value) setDate(event.target.value);
              }}
              sx={{ width: 142, "& .MuiInputBase-input": { fontSize: 12 } }}
              slotProps={{
                htmlInput: { max: localDate(), "aria-label": "请求日期" },
              }}
            />
          )}
          <Tooltip title="刷新请求记录">
            <span>
              <IconButton
                aria-label="刷新请求记录"
                disabled={loading || !active}
                onClick={refresh}
              >
                <RefreshRounded
                  sx={{
                    fontSize: 18,
                    ...(loading
                      ? {
                          animation: "request-spin 1s linear infinite",
                          "@keyframes request-spin": {
                            to: { transform: "rotate(360deg)" },
                          },
                        }
                      : {}),
                  }}
                />
              </IconButton>
            </span>
          </Tooltip>
          <Button
            variant="outlined"
            startIcon={<DownloadRounded sx={{ fontSize: "15px !important" }} />}
            disabled={!count || view === "network"}
            onClick={() => feed && exportRequests(feed)}
            title="导出当前加载的全部请求记录"
          >
            导出 CSV
          </Button>
        </Stack>
      </Stack>
      <ToggleButtonGroup
        exclusive
        value={view}
        onChange={(_, value) => {
          if (value) setView(value);
        }}
        size="small"
        aria-label="请求记录视图"
        sx={{ mx: 2, mb: 1, alignSelf: "flex-start", flexShrink: 0 }}
      >
        <ToggleButton value="usage">响应与用量</ToggleButton>
        <ToggleButton value="network">
          网络事件（{feed?.network?.total ?? 0}）
        </ToggleButton>
      </ToggleButtonGroup>
      {error && (
        <Alert
          severity="error"
          sx={{ mx: 2, mb: 1.2, flexShrink: 0 }}
          action={
            <Button color="inherit" disabled={loading} onClick={refresh}>
              重试
            </Button>
          }
        >
          {error}
        </Alert>
      )}
      {feed &&
        !feed.timing_coverage &&
        [
          "restart_required",
          "configured",
          "awaiting_events",
          "awaiting_request_events",
        ].includes(feed.timing_status || "") && (
          <Alert severity="info" sx={{ mx: 2, mb: 1.2 }}>
            本机请求计时已配置，正在等待新请求事件。请求完成并导出事件后会自动更新；旧记录缺失的时间无法追补。
          </Alert>
        )}
      {feed &&
        !feed.timing_coverage &&
        ["collecting", "receiving_requests"].includes(
          feed.timing_status || ""
        ) && (
          <Alert severity="info" sx={{ mx: 2, mb: 1.2, flexShrink: 0 }}>
            {feed.timing_status === "receiving_requests"
              ? "本机接收器正在接收请求事件，计时以当前范围的实际覆盖为准。"
              : "本机接收器已收到事件，正在等待可关联的请求事件。"}
            批量导出会有延迟，完成关联后自动更新。
          </Alert>
        )}
      {feed?.timing_status === "external_exporter" && (
        <Alert severity="info" sx={{ mx: 2, mb: 1.2 }}>
          已保留现有事件导出配置，本机计时未接入。缺少请求事件的记录显示 —。
        </Alert>
      )}
      {feed?.skipped_files ? (
        <Alert severity="warning" sx={{ mx: 2, mb: 1.2, flexShrink: 0 }}>
          {feed.skipped_files} 个本机记录文件未能读取，列表可能不完整。
        </Alert>
      ) : null}
      {loading && !feed && (
        <LinearProgress aria-label="正在读取请求记录" sx={{ flexShrink: 0 }} />
      )}
      {view === "network" ? (
        <NetworkEvents feed={feed?.network} />
      ) : (
        <>
          <TableContainer sx={{ flex: 1, minHeight: 70 }}>
            <Table
              stickyHeader
              size="small"
              aria-label="单次请求明细"
              sx={{
                minWidth: 700,
                tableLayout: "fixed",
                "& td": { py: 0.45, px: 0.75 },
                "& th": { px: 0.75, fontSize: 10, whiteSpace: "nowrap" },
                "& td .MuiTypography-root": { lineHeight: 1.4 },
              }}
            >
              <colgroup>
                {[9, 17, 14, 9, 13, 18, 8, 12].map((width, index) => (
                  <col key={index} style={{ width: width + "%" }} />
                ))}
              </colgroup>
              <TableHead>
                <TableRow>
                  <TableCell>时间</TableCell>
                  <TableCell>模型 / 强度</TableCell>
                  <TableCell align="right">估算费用 (USD)</TableCell>
                  <TableCell align="right">
                    <Tooltip title={timingDescription}>
                      <span>TPS ⓘ</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={timingDescription}>
                      <span>首响 / 耗时 ⓘ</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">Token 消耗</TableCell>
                  <TableCell align="right">缓存率</TableCell>
                  <TableCell align="center">会话</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {requests.slice(start, start + rowsPerPage).map((row) => {
                  const time = clockTime(row.timestamp);
                  const tps = observedTps(row);
                  const firstResponse = row.first_response_seconds;
                  const duration = row.duration_seconds;
                  const cacheRate =
                    row.input_tokens > 0
                      ? (row.cached_input_tokens / row.input_tokens) * 100
                      : null;
                  const cost = row.estimated_cost;
                  return (
                    <TableRow hover key={row.id}>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
                        <Typography
                          variant="caption"
                          color="textSecondary"
                          sx={{
                            fontFamily: mono,
                            display: "block",
                            lineHeight: 1.4,
                          }}
                        >
                          {time.day}
                        </Typography>
                        <Typography
                          sx={{
                            fontFamily: mono,
                            fontSize: 11,
                            lineHeight: 1.4,
                          }}
                        >
                          {time.time}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ maxWidth: 220 }}>
                        <Typography
                          noWrap
                          title={row.model}
                          sx={{
                            fontFamily: mono,
                            fontWeight: 650,
                            fontSize: 11,
                          }}
                        >
                          {row.model || "未知模型"}
                        </Typography>
                        <Stack direction="row" spacing={0.5} sx={{ mt: 0.35 }}>
                          {row.reasoning_effort && (
                            <Chip
                              label={row.reasoning_effort}
                              sx={{
                                height: 16,
                                fontSize: 9,
                                bgcolor: "action.selected",
                                color: "primary.main",
                                "& .MuiChip-label": { px: 0.6 },
                              }}
                            />
                          )}
                          <Chip
                            label="Standard"
                            sx={{
                              height: 16,
                              fontSize: 9,
                              bgcolor: "action.hover",
                              color: "text.secondary",
                              "& .MuiChip-label": { px: 0.6 },
                            }}
                          />
                        </Stack>
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          whiteSpace: "nowrap",
                          fontFamily: mono,
                          fontWeight: 600,
                        }}
                      >
                        <Tooltip
                          title={
                            cost == null
                              ? "该模型或用量无法定价"
                              : "按公开 API Standard 价格估算，不代表实际扣费"
                          }
                        >
                          <span>
                            {cost == null || !Number.isFinite(cost)
                              ? "—"
                              : money(cost, 6)}
                          </span>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                        <Tooltip title={timingDescription}>
                          <Box>
                            <Typography
                              sx={{
                                fontFamily: mono,
                                fontSize: 12,
                                fontWeight: 600,
                                color: tpsColor(tps),
                              }}
                            >
                              {tps == null ? "—" : tps.toFixed(1)}
                              {tps != null && (
                                <Typography
                                  component="span"
                                  variant="caption"
                                  color="textSecondary"
                                >
                                  {" "}
                                  tok/s
                                </Typography>
                              )}
                            </Typography>
                          </Box>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                        <Tooltip title={timingDescription}>
                          <Box>
                            <Typography
                              variant="caption"
                              color="textSecondary"
                              sx={{ fontFamily: mono, display: "block" }}
                            >
                              首响{" "}
                              <Box
                                component="span"
                                sx={{ color: elapsedTimeColor(firstResponse) }}
                              >
                                {elapsed(firstResponse)}
                              </Box>
                            </Typography>
                            <Typography
                              variant="caption"
                              color="textSecondary"
                              sx={{ fontFamily: mono, display: "block" }}
                            >
                              耗时{" "}
                              <Box
                                component="span"
                                sx={{ color: elapsedTimeColor(duration) }}
                              >
                                {elapsed(duration)}
                              </Box>
                            </Typography>
                          </Box>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right">
                        <TokenConsumption {...row} />
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          fontFamily: mono,
                          fontWeight: 600,
                          whiteSpace: "nowrap",
                          color: "success.main",
                        }}
                      >
                        {cacheRate == null ? "—" : `${cacheRate.toFixed(1)}%`}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={
                            row.session_id ? row.session_id.slice(0, 8) : "—"
                          }
                          variant="outlined"
                          sx={{
                            fontFamily: mono,
                            height: 20,
                            fontSize: 9,
                            color: "primary.main",
                            borderColor: "divider",
                            bgcolor: "action.hover",
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <Box
            sx={{
              px: 2,
              borderTop: "1px solid",
              borderColor: "divider",
              flexShrink: 0,
              display: "flex",
              flexDirection: { xs: "column-reverse", sm: "row" },
              alignItems: { sm: "center" },
              gap: { xs: 0, sm: 1 },
            }}
          >
            <Typography
              variant="caption"
              color="textSecondary"
              sx={{ flex: 1, py: 0.8, lineHeight: 1.5 }}
            >
              按本机单次模型响应记录；同 Provider 下账号合并统计。TPS
              为请求平均输出速率， 含等待；费用为 API 等价估算，不代表账单。
            </Typography>
            <TablePagination
              component="div"
              count={count}
              page={safePage}
              rowsPerPage={rowsPerPage}
              onPageChange={(_, next) => setPage(next)}
              onRowsPerPageChange={(event) =>
                setRowsPerPage(Number(event.target.value))
              }
              rowsPerPageOptions={[8, 15, 30, 50]}
              labelRowsPerPage="每页"
              labelDisplayedRows={({ from, to, count }) =>
                `${from}–${to} / ${count} 次记录`
              }
              getItemAriaLabel={(type) =>
                type === "next" ? "下一页" : "上一页"
              }
              sx={{
                flexShrink: 0,
                "& .MuiTablePagination-toolbar": { minHeight: 44, px: 0 },
                "& .MuiTablePagination-selectLabel, & .MuiTablePagination-displayedRows":
                  { fontSize: 11, color: "text.secondary" },
              }}
            />
          </Box>
        </>
      )}
    </>
  );
}
