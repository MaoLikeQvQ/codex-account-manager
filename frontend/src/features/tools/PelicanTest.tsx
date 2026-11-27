import { useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, DialogActions,
  DialogContent, DialogTitle, Divider, Stack, TextField, Typography,
} from "@mui/material";
import Dialog from "../../shared/ui/ManagerDialog";
import { errorText } from "../../shared/api/client";
import { mono } from "../../shared/theme";
import type { Account, RequestApi } from "../../shared/types";

interface Result {
  account: string;
  model: string;
  reported_model: string;
  reasoning_effort: string;
  prompt: string;
  reply: string;
  preview_svg: string;
  warning: string;
  elapsed_ms: number;
}
const prompt = "Draw an SVG of a pelican riding a bicycle. Return only a complete, self-contained SVG, without Markdown fences, scripts, external images, or external resources.";

function download(result: Result) {
  const url = URL.createObjectURL(new Blob([result.reply], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "maox-pelican-original.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function PelicanTest({
  account, currentModel, api, busy, onModalChange,
}: {
  account?: Account;
  currentModel: string;
  api: RequestApi;
  busy: boolean;
  onModalChange: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const pending = useRef(false);
  const model = currentModel;
  useEffect(() => {
    setResult(null);
    setError("");
  }, [account?.name, account?.updated_at, model]);
  useEffect(() => {
    if (!running) return;
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);
  function show() {
    setOpen(true);
    onModalChange(true);
  }
  function close() {
    if (pending.current) return;
    setOpen(false);
    onModalChange(false);
  }
  async function run() {
    if (pending.current || !account || !model || account.pending_apply) return;
    pending.current = true;
    setRunning(true);
    setElapsed(0);
    setError("");
    setResult(null);
    try {
      const response = await api<Result>("/api/benchmark/pelican", { account: account.name, model });
      if (!response.result) throw new Error("测试没有返回结果");
      setResult(response.result);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      pending.current = false;
      setRunning(false);
    }
  }
  return (
    <>
      <Button variant="outlined" disabled={busy || !account} onClick={show}>鹈鹕测试</Button>
      <Dialog open={open} onClose={close} maxWidth="md" aria-labelledby="pelican-title">
        <DialogTitle id="pelican-title">降智测试 · 鹈鹕骑自行车</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
              <Chip label={account?.name || "未启用账号"} variant="outlined" />
              <Chip label={model || "未设置默认模型"} sx={{ fontFamily: mono }} />
              <Chip label={`推理强度 ${account?.reasoning_effort || "high"}`} variant="outlined" />
            </Stack>
            <Typography variant="body2" color="textSecondary">
              用当前配置的模型生成 SVG，直观看图形理解、空间关系和代码绘图表现。单次结果不能证明模型身份或是否降智。
            </Typography>
            <Box sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1.5 }}>
              <Typography variant="caption" color="textSecondary">固定提示词</Typography>
              <Typography variant="body2" sx={{ fontFamily: mono, mt: 0.5, overflowWrap: "anywhere" }}>{prompt}</Typography>
            </Box>
            {!result && !running && <Alert severity="info">点击开始将向当前账号的服务发送 1 次模型请求，可能消耗额度；不会自动重试。超时或失败也可能已经产生用量。</Alert>}
            {account?.pending_apply && <Alert severity="warning">当前账号有待应用修改，请先应用后再测试。</Alert>}
            {!model && <Alert severity="warning">请先在 Codex 配置中设置模型。</Alert>}
            {running && <Alert icon={<CircularProgress size={18} />} severity="info">正在绘制 · 已等待 {elapsed} 秒。超时会显示错误，请勿重复提交。</Alert>}
            {error && <Alert severity="error">{error}</Alert>}
            {result && <>
              <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
                <Chip label={`耗时 ${(result.elapsed_ms / 1000).toFixed(1)} 秒`} variant="outlined" />
                <Chip label={`请求模型 ${result.model}`} variant="outlined" />
                {result.reported_model && <Chip label={`接口返回 ${result.reported_model}`} variant="outlined" />}
              </Stack>
              {result.warning && <Alert severity="warning">{result.warning}</Alert>}
              {result.preview_svg && <Box sx={{ bgcolor: "#fff", border: "1px solid", borderColor: "divider", borderRadius: 2, overflow: "hidden" }}>
                <Box component="img" alt="鹈鹕骑自行车测试结果" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(result.preview_svg)}`} sx={{ display: "block", width: "100%", height: { xs: 260, sm: 380 }, objectFit: "contain" }} />
              </Box>}
              <Typography variant="caption" color="textSecondary">观察：鹈鹕的长喙与喉囊是否可辨认；双轮与车架是否合理；身体、腿、踏板、车把的关系是否自然。接口返回的模型名仅为服务方自报。</Typography>
              <Divider />
              <TextField label="原始回答" value={result.reply} multiline minRows={5} maxRows={12} slotProps={{ input: { readOnly: true, sx: { fontFamily: mono, fontSize: 12 } } }} />
            </>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ flexWrap: "wrap" }}>
          {result && <Button onClick={() => download(result)}>导出原始回答</Button>}
          <Box sx={{ flex: 1 }} />
          <Button onClick={close} disabled={running}>关闭</Button>
          <Button variant="contained" onClick={() => void run()} disabled={running || busy || !account || !model || account.pending_apply}>
            {running ? "测试中…" : result ? "重新测试（1 次请求）" : "开始测试（1 次请求）"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
