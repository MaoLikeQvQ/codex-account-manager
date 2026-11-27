import NetworkEvents from "./NetworkEvents";
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import { money, tokens } from "../../shared/lib/format";
import { TokenConsumption } from "../../shared/usage/TokenConsumption";
import { elapsedTimeColor, mono, tpsColor } from "../../shared/theme";
import type { Account, RequestFeed, RequestRow } from "../../shared/types";

interface Props {
  feed: RequestFeed | null;
  loading: boolean;
  error: string;
  refresh: () => void;
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

export default function RequestsPanel({
  feed,
  loading,
  error,
  refresh,
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

  useEffect(() => {
    setPage(0);
  }, [active?.name, rowsPerPage]);

  return (
    <>
      <Stack
        direction="row"
        spacing={1.5}
        sx={{
          px: 2,
          py: 1.25,
          justifyContent: "space-between",
          alignItems: { sm: "center" },
          flexShrink: 0,
        }}
      >
        <ToggleButtonGroup
          exclusive
          value={view}
          onChange={(_, value) => {
            if (value) setView(value);
          }}
          size="small"
          aria-label="请求记录视图"
          sx={{ alignSelf: "flex-start", flexShrink: 0 }}
        >
          <ToggleButton value="usage" title="当前 Provider 今天的本机请求，最多加载最新 100 条；缺失的计时无法追补。">响应与用量</ToggleButton>
          <ToggleButton value="network" title="所有 Provider 今天已采集的网络事件，含失败和重试，不计入用量。HTTP 成功仅代表收到响应头；事件耗时不等于整轮耗时。">
            网络事件（{feed?.network?.total ?? 0}）
          </ToggleButton>
        </ToggleButtonGroup>
        <Tooltip title="刷新请求记录">
          <span>
            <IconButton
              aria-label="刷新请求记录"
              disabled={loading || !active}
              onClick={refresh}
            >
              <RefreshRounded sx={{ fontSize: 18 }} />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
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
              justifyContent: "flex-end",
              gap: { xs: 0, sm: 1 },
            }}
          >
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
