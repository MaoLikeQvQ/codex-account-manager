import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from "@mui/material";
import type { NetworkFeed } from "./types";
import { mono } from "./theme";

const statusLabels: Record<string, string> = {
  failed: "失败",
  completed: "响应完成",
  response_received: "已收到响应头",
  unknown: "结果未上报",
};
const errorLabels: Record<string, string> = {
  timeout: "请求超时",
  dns: "域名解析失败",
  tls: "TLS / 证书错误",
  connection: "网络连接异常",
  authorization: "授权错误",
  rate_limit: "限流或额度不足",
  request_error: "请求错误（详情未保存）",
};
function exportEvents(feed: NetworkFeed) {
  const cell = (value: unknown) => {
    let text = value == null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const columns = [
    "时间",
    "模型",
    "传输",
    "目标地址",
    "HTTP状态",
    "结果",
    "错误分类",
    "耗时ms",
    "会话",
    "事件",
  ];
  const rows = feed.events.map((row) => [
    row.timestamp,
    row.model,
    row.transport,
    row.endpoint,
    row.http_status,
    statusLabels[row.status],
    errorLabels[row.error_category] || "",
    row.duration_ms,
    row.session_id,
    row.event,
  ]);
  const url = URL.createObjectURL(
    new Blob(
      [
        "\uFEFF" +
          [columns, ...rows].map((row) => row.map(cell).join(",")).join("\r\n"),
      ],
      { type: "text/csv;charset=utf-8;" }
    )
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "maox-network-events.csv";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function NetworkEvents({ feed }: { feed?: NetworkFeed }) {
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(15);
  const events = feed?.events || [];
  const safePage = Math.min(
    page,
    Math.max(0, Math.ceil(events.length / size) - 1)
  );
  return (
    <>
      <Alert severity="info" sx={{ mx: 2, mb: 1, flexShrink: 0, py: 0.5 }}>
        显示所有 Provider 已采集的 Codex
        网络事件，包含失败及重试，不计入用量记录。HTTP
        成功仅代表收到响应头；流结束事件单独列出，事件耗时不等于整轮耗时。
        未接入事件导出的进程、管理器关闭期间以及尚未导出的事件可能缺失。未上报的目标地址和错误原因无法追补。
      </Alert>
      <Stack
        direction="row"
        sx={{
          px: 2,
          mb: 1,
          flexShrink: 0,
          gap: 1,
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Typography variant="caption" color="textSecondary">
          共 {feed?.total || 0} 个事件 · 展示最新 {events.length} 个 ·
          不保存正文、授权头及 URL 参数
        </Typography>
        <Button
          variant="outlined"
          disabled={!events.length}
          onClick={() => feed && exportEvents(feed)}
        >
          导出网络 CSV
        </Button>
      </Stack>
      <TableContainer sx={{ flex: 1, minHeight: 70 }}>
        <Table
          stickyHeader
          size="small"
          aria-label="网络请求事件"
          sx={{
            minWidth: 650,
            tableLayout: "fixed",
            "& td": {
              py: 0.75,
              px: 1,
              verticalAlign: "top",
              overflowWrap: "anywhere",
            },
            "& th": { px: 1 },
          }}
        >
          <colgroup>
            {[21, 21, 24, 23, 11].map((width, index) => (
              <col key={index} style={{ width: width + "%" }} />
            ))}
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell>时间 / 会话</TableCell>
              <TableCell>模型 / 传输</TableCell>
              <TableCell>目标地址</TableCell>
              <TableCell>状态 / 原因</TableCell>
              <TableCell align="right">事件耗时</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {events.slice(safePage * size, (safePage + 1) * size).map((row) => (
              <TableRow key={row.id} hover>
                <TableCell>
                  <Typography sx={{ fontFamily: mono, fontSize: 12 }}>
                    {new Date(row.timestamp).toLocaleString("zh-CN", {
                      hour12: false,
                    })}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="textSecondary"
                    title={row.session_id}
                  >
                    {row.session_id.slice(0, 8) || "会话未上报"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {row.model || "模型未上报"}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {row.transport} · {row.kind || "请求尝试"}
                  </Typography>
                </TableCell>
                <TableCell sx={{ maxWidth: 300 }}>
                  <Box
                    sx={{
                      fontFamily: mono,
                      fontSize: 12,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {row.endpoint || "未上报"}
                  </Box>
                  {row.endpoint.startsWith("/") && (
                    <Typography variant="caption" color="textSecondary">
                      主机未上报
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={
                      row.status === "failed"
                        ? "error"
                        : row.status === "completed"
                        ? "success"
                        : "default"
                    }
                    label={
                      (row.http_status ? row.http_status + " · " : "") +
                      (statusLabels[row.status] || "未知")
                    }
                  />
                  {row.status === "failed" && (
                    <Typography
                      variant="caption"
                      color="error"
                      sx={{ display: "block", mt: 0.5 }}
                    >
                      {errorLabels[row.error_category] ||
                        (row.http_status ? "HTTP 请求失败" : "失败原因未上报")}
                    </Typography>
                  )}
                </TableCell>
                <TableCell
                  align="right"
                  sx={{ fontFamily: mono, whiteSpace: "nowrap" }}
                >
                  {row.duration_ms == null
                    ? "—"
                    : (row.duration_ms / 1000).toFixed(2) + "s"}
                </TableCell>
              </TableRow>
            ))}
            {!events.length && (
              <TableRow>
                <TableCell colSpan={5} sx={{ py: 5, textAlign: "center" }}>
                  暂无网络事件。完整退出并重新打开 Codex
                  后发送新请求，等待事件导出。
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={events.length}
        page={safePage}
        rowsPerPage={size}
        rowsPerPageOptions={[15, 30, 50]}
        onPageChange={(_, value) => setPage(value)}
        onRowsPerPageChange={(event) => {
          setSize(Number(event.target.value));
          setPage(0);
        }}
        labelRowsPerPage="每页"
        sx={{
          flexShrink: 0,
          "& .MuiTablePagination-toolbar": { minHeight: 40 },
        }}
      />
    </>
  );
}
