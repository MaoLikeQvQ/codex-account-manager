import Dialog from "../../shared/ui/ManagerDialog";
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import ImageOutlined from "@mui/icons-material/ImageOutlined";
import SystemUpdateAltRounded from "@mui/icons-material/SystemUpdateAltRounded";
import { errorText } from "../../shared/api/client";
import type { AppState, Notify, RequestApi } from "../../shared/types";
import PelicanTest from "./PelicanTest";
import ScienceOutlined from "@mui/icons-material/ScienceOutlined";

interface UpdateResult {
  enabled?: boolean;
  available: boolean;
  current_version: string;
  version?: string;
  message?: string;
}
interface Props {
  state: AppState;
  api: RequestApi;
  notify: Notify;
  busy: boolean;
  onModalChange: (open: boolean) => void;
}

export default function ToolsPanel({
  state,
  api,
  notify,
  busy,
  onModalChange,
}: Props) {
  const [imageOpen, setImageOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<
    "image" | "update" | null
  >(null);
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [update, setUpdate] = useState<UpdateResult | null>(null);
  const [updateError, setUpdateError] = useState("");
  const [checking, setChecking] = useState(false);
  const [source, setSource] = useState("managed_account");
  const [account, setAccount] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [imageError, setImageError] = useState("");
  const active = state.accounts.find((item) => item.active);
  const imageAccounts = state.accounts.filter(
    (item) => item.account_type === "custom",
  );
  const image = state.image_generation;
  const updatesEnabled = document.body.dataset.updatesEnabled === "true";
  const alive = useRef(true);
  const checkInFlight = useRef(false);
  const disabled = busy || working;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      onModalChange(false);
    };
  }, [onModalChange]);
  useEffect(() => {
    onModalChange(imageOpen || testOpen || !!confirmation || working);
  }, [imageOpen, testOpen, confirmation, working, onModalChange]);

  async function checkUpdates() {
    if (!updatesEnabled || checkInFlight.current) return;
    checkInFlight.current = true;
    setChecking(true);
    setUpdateError("");
    try {
      const response = await api<UpdateResult>("/api/updates");
      if (alive.current) setUpdate(response.result ?? null);
    } catch (failure) {
      if (alive.current) setUpdateError(errorText(failure));
    } finally {
      checkInFlight.current = false;
      if (alive.current) setChecking(false);
    }
  }
  useEffect(() => {
    void checkUpdates();
  }, []);

  function openImage() {
    setSource(
      image.source === "separate" || !imageAccounts.length
        ? "separate"
        : "managed_account",
    );
    setAccount(
      imageAccounts.find((item) => item.name === image.account_name)?.name ||
        imageAccounts.find((item) => item.active)?.name ||
        imageAccounts[0]?.name ||
        "",
    );
    setBaseUrl(image.base_url || "https://api.openai.com/v1");
    setKey("");
    setModel(image.image_model || "gpt-image-2");
    setEnabled(image.enabled !== false);
    setImageError("");
    setImageOpen(true);
  }
  function closeImage() {
    if (!working) {
      setImageOpen(false);
      setKey("");
    }
  }
  async function saveImage(event: React.FormEvent) {
    event.preventDefault();
    setWorking(true);
    setImageError("");
    try {
      const response = await api("/api/image-generation/configure", {
        enabled,
        source,
        account_name: account,
        base_url: baseUrl,
        api_key: key,
        mode: "images",
        image_model: model,
      });
      setImageOpen(false);
      setKey("");
      notify(response.message || "Custom ImageGen 配置已保存，请点击应用");
    } catch (failure) {
      setImageError(errorText(failure));
    } finally {
      setWorking(false);
    }
  }
  async function execute() {
    const operation = confirmation;
    setConfirmation(null);
    setWorking(true);
    setResult(null);
    const config =
      operation === "image"
        ? {
            path: "/api/image-generation/apply",
            body: {},
            label: "应用 Custom ImageGen",
          }
        : { path: "/api/updates/download", body: {}, label: "更新应用" };
    try {
      const response = await api<{ message?: string }>(
        config.path,
        config.body,
      );
      const message =
        response.message || response.result?.message || `${config.label}完成`;
      setResult({ message, error: Boolean(response.warning) });
      notify(message, response.warning);
    } catch (failure) {
      const message = errorText(failure);
      setResult({ message, error: true });
      notify(message, true);
    } finally {
      setWorking(false);
    }
  }
  return (
    <Box sx={{ pb: 2 }}>
      <Typography variant="caption" color="textSecondary" sx={{ px: 0.5 }}>模型与扩展</Typography>
      <Stack spacing={1.5} sx={{ mt: 1 }}>
        <ToolRow
          icon={<ScienceOutlined />}
          title="降智测试"
          description="让当前配置的模型绘制鹈鹕骑自行车，查看 SVG 结果、原始回答与耗时。"
        >
          <PelicanTest account={active} currentModel={state.current.model} api={api} busy={disabled} onModalChange={setTestOpen} />
        </ToolRow>
        <ToolRow
          icon={<ImageOutlined />}
          title="Custom ImageGen"
          description={
            image.configured
              ? `${image.account_name || image.image_model} · ${image.installed_version ? `已安装 v${image.installed_version}` : "尚未安装"}${image.pending_apply ? " · 待应用" : ""}`
              : "连接已管理账号或专用图片渠道，供 Codex 使用。"
          }
        >
          <Button variant="outlined" onClick={openImage} disabled={disabled}>
            配置
          </Button>
          <Button
            variant="contained"
            onClick={() => setConfirmation("image")}
            disabled={
              disabled || (!image.configured && image.enabled !== false)
            }
          >
            应用
          </Button>
        </ToolRow>
      </Stack>
      <Typography variant="caption" color="textSecondary" component="div" sx={{ mt: 2.5, mb: 1, px: 0.5 }}>系统与更新</Typography>
      <Stack spacing={1.5}>
        <ToolRow
          icon={<SystemUpdateAltRounded />}
          title="应用更新"
          description={
            !updatesEnabled
              ? "开发模式 · 不检查应用更新"
              : checking
                ? "正在检查最新版本…"
                : updateError ||
                  (update
                    ? update.available
                      ? `当前 ${update.current_version} · 新版 ${update.version} 可用`
                      : `当前 ${update.current_version} · 已是最新版本`
                    : "检查 GitHub 发布的新版本。")
          }
        >
          <Button
            variant="outlined"
            onClick={() => void checkUpdates()}
            disabled={disabled || checking || !updatesEnabled}
          >
            检查更新
          </Button>
          {update?.available && (
            <Button
              variant="contained"
              onClick={() => setConfirmation("update")}
              disabled={disabled}
            >
              更新并重启
            </Button>
          )}
        </ToolRow>
      </Stack>
      {!image.runtime_available && (
        <Alert severity="info" sx={{ mt: 1.5 }}>
          图片工具运行需要 Node.js。安装后重新打开管理器，再应用图片配置。
        </Alert>
      )}
      {working && (
        <Alert
          icon={<CircularProgress size={17} />}
          severity="info"
          sx={{ mt: 1.5 }}
        >
          正在处理，请等待操作完成。
        </Alert>
      )}
      {result && (
        <Alert severity={result.error ? "error" : "success"} sx={{ mt: 1.5 }}>
          {result.message}
        </Alert>
      )}
      <Box
        sx={{
          mt: 3,
          px: 1.5,
          py: 1.2,
          bgcolor: "action.hover",
          borderRadius: 1,
        }}
      >
        <Typography variant="caption" color="textSecondary">
          账号保存仅更新档案，使用账号才会写入 Codex
          配置。历史会在安全时自动归属到当前账号。图片配置保存后，点击“应用”并重启 Codex
          生效。
        </Typography>
      </Box>

      <Dialog
        open={imageOpen}
        onClose={closeImage}
        aria-labelledby="image-config-title"
      >
        <Box component="form" onSubmit={saveImage}>
          <DialogTitle id="image-config-title">Custom ImageGen</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2} sx={{ pt: 0.5 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={enabled}
                    onChange={(event) => setEnabled(event.target.checked)}
                    disabled={working}
                  />
                }
                label="启用 Custom ImageGen"
              />
              {enabled && (
                <>
                  <TextField
                    select
                    label="凭据来源"
                    value={source}
                    onChange={(event) => setSource(event.target.value)}
                    disabled={working}
                  >
                    <MenuItem
                      value="managed_account"
                      disabled={!imageAccounts.length}
                    >
                      已管理账号
                    </MenuItem>
                    <MenuItem value="separate">自定义链接</MenuItem>
                  </TextField>
                  {source === "managed_account" ? (
                    <TextField
                      required
                      select
                      label="使用账号"
                      value={account}
                      onChange={(event) => setAccount(event.target.value)}
                      disabled={working}
                    >
                      {imageAccounts.map((item) => (
                        <MenuItem key={item.name} value={item.name}>
                          {item.name} · 兼容渠道
                        </MenuItem>
                      ))}
                    </TextField>
                  ) : (
                    <>
                      <TextField
                        required
                        type="url"
                        label="图片服务地址"
                        value={baseUrl}
                        onChange={(event) => setBaseUrl(event.target.value)}
                        disabled={working}
                      />
                      <TextField
                        required={!image.has_api_key}
                        type="password"
                        label="图片 API Key"
                        value={key}
                        onChange={(event) => setKey(event.target.value)}
                        autoComplete="new-password"
                        helperText={
                          image.has_api_key
                            ? "留空保留已保存的专用 Key"
                            : "请输入图片服务的 API Key"
                        }
                        disabled={working}
                      />
                    </>
                  )}
                  <TextField
                    required
                    label="图片模型"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    disabled={working}
                  />
                  <Alert severity="info">
                    {source === "separate"
                      ? "通过 Images API 生成和编辑图片。官方 ChatGPT/Codex OAuth 不能用于公开图片 API，请使用渠道 Key 或 OpenAI Platform API Key。"
                      : "图片工具固定使用所选兼容账号的服务地址和 API Key，仅影响图片工具。"}
                  </Alert>
                </>
              )}
              {imageError && (
                <Alert severity="error" role="alert">
                  {imageError}
                </Alert>
              )}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={closeImage} disabled={working}>
              取消
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={
                working || (enabled && source === "managed_account" && !account)
              }
            >
              {working ? "保存中…" : "保存配置"}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
      <Dialog
        open={!!confirmation}
        onClose={() => setConfirmation(null)}
        aria-labelledby="tool-confirm-title"
      >
        <DialogTitle id="tool-confirm-title">
          {confirmation === "image" ? "应用 Custom ImageGen" : "安装更新并重启"}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {confirmation === "image"
              ? "比较并安装或更新图片插件，同时应用当前图片配置。完成后需要重启 Codex。"
              : "下载并校验新版后，管理器会自动退出、安装并重新打开。请先保存编辑内容。"}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setConfirmation(null)}>
            取消
          </Button>
          <Button variant="contained" onClick={() => void execute()}>
            确认执行
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function ToolRow({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={2}
      sx={{ alignItems: { xs: "stretch", sm: "center" }, p: 2.25, bgcolor: "background.paper", borderRadius: "16px", boxShadow: "0 3px 14px #20243404" }}
    >
      <Box
        sx={{
          display: "flex",
          color: "primary.main",
          bgcolor: "action.hover",
          p: 0.8,
          borderRadius: "9px",
          "& svg": { fontSize: 20 },
          alignSelf: "flex-start",
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle2">{title}</Typography>
        <Typography variant="caption" color="textSecondary">
          {description}
        </Typography>
      </Box>
      <Stack direction="row" spacing={1}>
        {children}
      </Stack>
    </Stack>
  );
}
