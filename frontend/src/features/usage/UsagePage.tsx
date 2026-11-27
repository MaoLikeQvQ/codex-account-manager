import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  IconButton,
  InputAdornment,
  LinearProgress,
  Link,
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
import InfoOutlined from "@mui/icons-material/InfoOutlined";
import { localDate } from "../../shared/lib/date";
import { money, tokens } from "../../shared/lib/format";
import { TokenConsumption } from "../../shared/usage/TokenConsumption";
import { mono } from "../../shared/theme";
import type { Account, Usage } from "../../shared/types";

export function UsagePage({
  usage,
  error,
  loading,
  period,
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
    const range = period === "all" ? "all" : usage?.date ?? localDate();
    const end = usage && usage.end_date !== usage.date ? `-to-${usage.end_date}` : "";
    link.download = `maox-usage-${range}${end}.csv`;
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
        <Typography variant="subtitle2">模型用量明细</Typography>
        <Stack
          sx={{ alignItems: "center", flexWrap: "wrap" }}
          direction="row"
          spacing={0.8}
          useFlexGap
        >
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
          <Tooltip
            describeChild
            title={
              <Box sx={{ maxWidth: 330 }}>
                <Typography variant="caption" component="div">
                  按当前 Provider 汇总本机记录，同 Provider 下账号合并统计。
                  思考已包含在输出中。费用按 API Standard 价格估算，不代表实际账单或订阅扣费。
                </Typography>
                {usage?.pricing?.updated_at && (
                  <Typography variant="caption" component="div">
                    最近同步于{" "}
                    {new Date(usage.pricing.updated_at * 1000).toLocaleString(
                      "zh-CN", { hour12: false }
                    )}
                  </Typography>
                )}
                <Link
                  href={usage?.price_source || "https://developers.openai.com/api/docs/pricing"}
                  target="_blank"
                  rel="noopener noreferrer"
                  color="inherit"
                >
                  价格来源 ↗
                </Link>
              </Box>
            }
          >
            <IconButton aria-label="用量统计与价格说明" size="small">
              <InfoOutlined sx={{ fontSize: 17 }} />
            </IconButton>
          </Tooltip>
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
      {usage?.pricing?.warning && (
        <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
          {usage.pricing.warning}
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
    </>
  );
}
