import { useState } from "react";
import {
  Box,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from "@mui/material";
import type { NetworkFeed } from "../../shared/types";
import { mono } from "../../shared/theme";

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
