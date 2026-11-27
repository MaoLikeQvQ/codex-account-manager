import { useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, DialogActions, DialogContent,
  DialogTitle, Divider, Stack, Switch,
  TextField, Typography,
} from "@mui/material";
import Dialog from "../../shared/ui/ManagerDialog";
import { errorText } from "../../shared/api/client";
import type { RequestApi } from "../../shared/types";

interface WakeupState {
  enabled: boolean;
  times: string[];
  model: string;
  timezone: string;
  next_run: string | null;
  delay_minutes?: number;
  running: boolean;
  error: string;
  results: { account: string; status: string; message: string; at: string }[];
}
interface Props {
  api: RequestApi;
  defaultModel: string;
  officialCount: number;
  onClose: () => void;
}
const dateText = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "—";
const delayText = (minutes: number) => `${Math.floor(minutes / 60) ? `${Math.floor(minutes / 60)} 小时 ` : ""}${minutes % 60 ? `${minutes % 60} 分钟` : ""}`.trim();

export default function WakeupDialog({ api, defaultModel, officialCount, onClose }: Props) {
  const [state, setState] = useState<WakeupState | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [timeText, setTimeText] = useState("");
  const times = timeText.trim() ? timeText.split(/[,，]/).map((time) => time.trim()) : [];
  const [model, setModel] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirmRun, setConfirmRun] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  const initialized = useRef(false);
  const dirty = !!state && (enabled !== state.enabled || model !== state.model || JSON.stringify(times) !== JSON.stringify(state.times));

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    let controller: AbortController | undefined;
    setLoading(!initialized.current);
    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      controller = new AbortController();
      let timedOut = false;
      const timeout = window.setTimeout(() => {
        timedOut = true;
        controller?.abort();
      }, 10000);
      try {
        const response = await api<WakeupState>("/api/accounts/wakeup", undefined, { signal: controller.signal });
        if (!response.result) throw new Error("无法读取定时唤醒配置");
        if (!alive) return;
        setState(response.result);
        setLoadError("");
        if (!initialized.current) {
          initialized.current = true;
          setEnabled(response.result.enabled);
          setTimeText(response.result.times.join(","));
          setModel(response.result.model || defaultModel);
        }
      } catch (failure) {
        if (alive) setLoadError(timedOut ? "读取定时唤醒设置超时，请重试" : errorText(failure));
      } finally {
        window.clearTimeout(timeout);
        inFlight = false;
        if (alive) setLoading(false);
      }
    }
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => { alive = false; window.clearInterval(interval); controller?.abort(); };
  }, [api, defaultModel, retry]);

  async function save() {
    if (times.length > 48 || times.some((time) => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time))) { setError("请输入 HH:MM 格式的时间，用逗号分隔，最多 48 个"); return; }
    if (new Set(times).size !== times.length) { setError("发送时间不能重复"); return; }
    setWorking(true); setError(""); setNotice("");
    try {
      const response = await api<WakeupState>("/api/accounts/wakeup/configure", { enabled, times, model: model.trim() });
      if (!response.result) throw new Error("保存未返回结果");
      setState(response.result); setTimeText(response.result.times.join(",")); setModel(response.result.model);
      setNotice("定时唤醒设置已保存");
    } catch (failure) { setError(errorText(failure)); }
    finally { setWorking(false); }
  }
  async function run() {
    if (dirty || working || state?.running) return;
    setConfirmRun(false); setWorking(true); setError(""); setNotice("");
    try {
      const response = await api<WakeupState>("/api/accounts/wakeup/run", {});
      if (!response.result) throw new Error("启动未返回结果");
      setState(response.result); setNotice("已启动，正在逐个处理官方账号");
    } catch (failure) { setError(errorText(failure)); }
    finally { setWorking(false); }
  }
  return (
    <Dialog open onClose={() => { if (!working) onClose(); }} fullWidth maxWidth="sm" aria-labelledby="wakeup-title">
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 2 }}>
        <DialogTitle id="wakeup-title">定时唤醒</DialogTitle>
        <Switch checked={enabled} disabled={loading || working} onChange={(_, checked) => setEnabled(checked)} slotProps={{ input: { "aria-label": "启用定时唤醒" } }} />
      </Box>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="textSecondary">每天向 {officialCount} 个官方账号发送 hi</Typography>
          {loading && <CircularProgress size={22} aria-label="读取设置" />}
          {loadError && <Alert severity="error" action={<Button color="inherit" disabled={loading} onClick={() => setRetry((value) => value + 1)}>重试</Button>}>{loadError}</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
          {notice && <Alert severity="success">{notice}</Alert>}
          {state && <>
            <TextField label="请求模型" value={model} disabled={working} onChange={(event) => setModel(event.target.value)} size="small" />
            <TextField label="每日时间" value={timeText} disabled={working} onChange={(event) => setTimeText(event.target.value)} placeholder="06:00,11:00,16:00" helperText="24 小时制，多个时间用逗号分隔" size="small" />
            <Typography variant="body2" color="textSecondary">下次执行：{dateText(state.next_run)}</Typography>
            {!!state.delay_minutes && <Typography variant="body2" color="textSecondary">今日累计顺延：{delayText(state.delay_minutes)}</Typography>}
            {state.error && <Alert severity="warning">{state.error}</Alert>}
            {(state.running || state.results.length > 0) && <>
              <Divider />
              <Typography variant="subtitle2">{state.running ? "正在唤醒…" : "最近执行"}</Typography>
              <Stack spacing={1} sx={{ maxHeight: 160, overflowY: "auto" }}>
                {state.results.map((result) => <Stack key={result.account} spacing={0.25}>
                  <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
                    <Typography variant="body2" sx={{ overflowWrap: "anywhere", minWidth: 0 }}>{result.account}</Typography>
                    {result.at && <Typography variant="caption" color="textSecondary" sx={{ flexShrink: 0 }}>{dateText(result.at)}</Typography>}
                  </Stack>
                  <Typography variant="caption" color={result.status === "failed" ? "error" : "textSecondary"}>{result.message}</Typography>
                </Stack>)}
              </Stack>
            </>}
            <Box component="details" sx={{ color: "text.secondary", typography: "caption", "& summary": { cursor: "pointer", width: "fit-content" } }}>
              <summary>使用说明</summary>
              <Typography variant="caption" component="p" sx={{ mb: 0 }}>
                按本机时间（{state.timezone}）执行。电脑恢复或管理器启动后补执行当天最早错过的时间点，后续时间按累计延迟顺延；顺延至次日的时间点跳过，次日恢复原定时间。所有官方账号共用此模型，新账号自动参与，不切换当前账号。请求会消耗额度，不保证触发额度周期。
              </Typography>
            </Box>
            {confirmRun && !dirty && <Alert severity="warning" action={<Button color="inherit" onClick={() => void run()}>确认发送</Button>}>立即向所有官方账号发送 hi，会消耗额度。</Alert>}
          </>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button disabled={loading || working || !state || state.running || dirty || !officialCount || !state.model} onClick={() => setConfirmRun(!confirmRun)}>立即唤醒全部</Button>
        <Button onClick={onClose} disabled={working}>关闭</Button>
        <Button variant="contained" onClick={() => void save()} disabled={loading || working || !state}>{working ? "处理中…" : "保存设置"}</Button>
      </DialogActions>
    </Dialog>
  );
}
