import Dialog from "./ManagerDialog";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Link,
  MenuItem,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import CloseRounded from "@mui/icons-material/CloseRounded";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import ContentCopyRounded from "@mui/icons-material/ContentCopyRounded";
import { errorText } from "./api";
import type { Account, Notify, RequestApi } from "./types";

interface Props {
  account: Account | null;
  api: RequestApi;
  notify: Notify;
  onClose: () => void;
  disabled: boolean;
}
interface ParsedConfig {
  name: string;
  provider_id: string;
  base_url: string;
  default_model: string;
  reasoning_effort: string;
  provider_config: Record<string, unknown>;
  api_key_model_discovery: boolean;
  ignored_fields: string[];
}
interface DeviceLogin {
  login_id: string;
  user_code: string;
  verification_url: string;
}
interface LoginStatus {
  status: string;
  email?: string;
  error?: string;
}

export default function AccountDialog({
  account,
  api,
  notify,
  onClose,
  disabled,
}: Props) {
  const [kind, setKind] = useState<"official" | "custom">(
    account?.account_type ?? "official",
  );
  const [name, setName] = useState(account?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(account?.base_url ?? "");
  const [key, setKey] = useState("");
  const [model, setModel] = useState(account?.default_model ?? "");
  const [effort, setEffort] = useState(account?.reasoning_effort ?? "high");
  const [catalog, setCatalog] = useState(account?.model_catalog_url ?? "");
  const [discovery, setDiscovery] = useState(
    account?.api_key_model_discovery ?? false,
  );
  const [requiresAuth, setRequiresAuth] = useState(
    account?.requires_openai_auth ?? true,
  );
  const [configText, setConfigText] = useState("");
  const [authText, setAuthText] = useState("");
  const [parsedText, setParsedText] = useState("");
  const [provider, setProvider] = useState<Record<string, unknown> | null>(
    null,
  );
  const [importOpen, setImportOpen] = useState(!account);
  const [importNotice, setImportNotice] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [pending, setPending] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [login, setLogin] = useState<DeviceLogin | null>(null);
  const live = useRef(true);
  const loginRef = useRef("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const apiRef = useRef(api);
  const notifyRef = useRef(notify);
  const nameRef = useRef(name);
  const closeRef = useRef(onClose);
  apiRef.current = api;
  notifyRef.current = notify;
  nameRef.current = name;
  closeRef.current = onClose;
  const locked = disabled || Boolean(pending) || Boolean(login);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      clearTimeout(timer.current);
      const id = loginRef.current;
      loginRef.current = "";
      if (id)
        void apiRef
          .current("/api/accounts/official-login/cancel", { login_id: id })
          .catch((error) =>
            notifyRef.current(`取消授权失败：${errorText(error)}`, true),
          );
    };
  }, []);

  function payload() {
    return {
      original_name: account?.name ?? "",
      name,
      provider_name: name,
      base_url: baseUrl,
      api_key: key,
      default_model: model,
      reasoning_effort: effort,
      wire_api: "responses",
      connection_type: provider
        ? "openai_compatible"
        : account?.connection_type || "openai_compatible",
      auth_mode:
        !provider && account?.connection_type === "sub2api"
          ? requiresAuth
            ? "legacy"
            : "api_key"
          : "legacy",
      transport: provider ? "http_sse" : account?.transport || "http_sse",
      model_catalog_url: catalog,
      api_key_model_discovery: discovery,
      requires_openai_auth: requiresAuth,
      ...(provider ? { provider_config: provider } : {}),
    };
  }

  async function cancelSession() {
    clearTimeout(timer.current);
    const id = loginRef.current;
    loginRef.current = "";
    setLogin(null);
    if (id) {
      try {
        await apiRef.current("/api/accounts/official-login/cancel", {
          login_id: id,
        });
      } catch (error) {
        notifyRef.current(`取消授权失败：${errorText(error)}`, true);
      }
    }
  }

  async function close() {
    if (pending && pending !== "官方授权") return;
    await cancelSession();
    closeRef.current();
  }

  async function pollLogin(id: string) {
    if (!live.current || loginRef.current !== id) return;
    try {
      const result = await apiRef.current<LoginStatus>(
        `/api/accounts/official-login/status?login_id=${encodeURIComponent(id)}`,
      );
      if (!live.current || loginRef.current !== id) return;
      if (result.result?.status === "pending") {
        timer.current = setTimeout(() => void pollLogin(id), 1200);
        return;
      }
      if (result.result?.status !== "completed")
        throw new Error(result.result?.error || "官方登录失败，请重新授权");
      setPending("正在保存授权");
      const saved = await apiRef.current(
        "/api/accounts/official-login/complete",
        { login_id: id, name: nameRef.current },
      );
      if (!live.current || loginRef.current !== id) return;
      loginRef.current = "";
      setLogin(null);
      notifyRef.current(saved.message || "官方账号已添加");
      closeRef.current();
    } catch (error) {
      if (!live.current || loginRef.current !== id) return;
      setError(errorText(error));
      await cancelSession();
    } finally {
      if (live.current) setPending("");
    }
  }

  async function startLogin() {
    setError("");
    setNotice("");
    setPending("官方授权");
    try {
      const started = await api<DeviceLogin>(
        "/api/accounts/official-login/start",
        {},
      );
      const device = started.result;
      if (!device?.login_id) throw new Error("未收到官方登录信息，请重试");
      if (!live.current) {
        await api("/api/accounts/official-login/cancel", {
          login_id: device.login_id,
        });
        return;
      }
      loginRef.current = device.login_id;
      if (new URL(device.verification_url).protocol !== "https:")
        throw new Error("官方授权地址必须使用 HTTPS");
      setLogin(device);
      timer.current = setTimeout(() => void pollLogin(device.login_id), 1200);
    } catch (error) {
      if (live.current) {
        setError(errorText(error));
        await cancelSession();
      } else notifyRef.current(errorText(error), true);
    } finally {
      if (live.current) setPending("");
    }
  }

  function validate(requireModel = false) {
    const failures: Record<string, string> = {};
    if (!name.trim()) failures.name = "请输入账号名称";
    try {
      const url = new URL(baseUrl);
      if (
        !["https:", "http:"].includes(url.protocol) ||
        url.username ||
        url.password ||
        url.search ||
        url.hash
      )
        throw new Error();
    } catch {
      failures.baseUrl = "请输入有效的 HTTP 或 HTTPS 服务地址";
    }
    if (!key.trim() && !account?.has_api_key) failures.key = "请输入 API Key";
    if (requireModel && !model.trim()) failures.model = "请输入用于验证连接的模型";
    setInvalid(failures);
    if (Object.keys(failures).length) {
      requestAnimationFrame(() =>
        document
          .querySelector<HTMLInputElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return false;
    }
    return true;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked) return;
    if (kind === "official") {
      await startLogin();
      return;
    }
    if (configText.trim() && configText !== parsedText) {
      setImportOpen(true);
      setError("粘贴内容有变化，请先点击“识别并填入”，再保存。");
      return;
    }
    if (!validate()) return;
    setPending("保存账号");
    setError("");
    try {
      const result = await api("/api/accounts/save", payload());
      notify(result.message || "账号档案已保存");
      onClose();
    } catch (error) {
      setError(errorText(error));
    } finally {
      if (live.current) setPending("");
    }
  }

  async function parseConfig() {
    setPending("识别配置");
    setError("");
    setImportNotice("");
    try {
      let importedKey = authText.trim();
      if (importedKey.startsWith("```"))
        importedKey = importedKey.split("\n").slice(1, -1).join("\n").trim();
      if (importedKey.startsWith("{")) {
        let auth;
        try {
          auth = JSON.parse(importedKey);
        } catch {
          throw new Error("auth.json 格式不正确，请复制完整 JSON");
        }
        if (
          typeof auth.OPENAI_API_KEY !== "string" ||
          !auth.OPENAI_API_KEY.trim()
        )
          throw new Error(
            "auth.json 中缺少 OPENAI_API_KEY；官方账号请使用授权登录",
          );
        importedKey = auth.OPENAI_API_KEY.trim();
      }
      if (
        importedKey &&
        (/\s/.test(importedKey) || /你的|your.*key|API.?Key/i.test(importedKey))
      )
        throw new Error("请填写真实 API Key，不要使用教程中的占位文字");
      const response = await api<ParsedConfig>("/api/accounts/parse-config", {
        config_text: configText,
      });
      const parsed = response.result;
      if (!parsed) throw new Error("未能识别配置");
      if (!name.trim()) setName(parsed.name);
      setProvider(parsed.provider_config);
      setParsedText(configText);
      setBaseUrl(parsed.base_url);
      setModel(parsed.default_model);
      setEffort(parsed.reasoning_effort);
      setCatalog(String(parsed.provider_config.model_catalog_url ?? ""));
      setDiscovery(parsed.api_key_model_discovery);
      setRequiresAuth(parsed.provider_config.requires_openai_auth !== false);
      if (importedKey) setKey(importedKey);
      setAuthText("");
      setInvalid({});
      setImportOpen(false);
      setImportNotice(
        `已识别 ${parsed.provider_id}，应用时统一使用 MaoLocal。${parsed.ignored_fields.length ? `未导入字段：${parsed.ignored_fields.join("、")}。` : ""}请检查后保存。`,
      );
    } catch (error) {
      setError(errorText(error));
    } finally {
      setPending("");
    }
  }

  async function verify(inference: boolean) {
    if (!validate(inference)) return;
    setPending(inference ? "验证连接" : "读取模型列表");
    setError("");
    setNotice("");
    try {
      const response = await api<{ model_ids: string[] }>(
        inference ? "/api/accounts/verify-connection" : "/api/accounts/verify",
        payload(),
      );
      if (!inference && response.result?.model_ids) {
        setModels(response.result.model_ids);
        if (!model) setModel(response.result.model_ids[0] || "");
      }
      setNotice(response.message || "操作完成");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setPending("");
    }
  }

  return (
    <Dialog
      open
      fullWidth
      maxWidth="sm"
      onClose={() => void close()}
      aria-labelledby="account-dialog-title"
      scroll="paper"
    >
      <Box component="form" noValidate onSubmit={submit}>
        <DialogTitle
          id="account-dialog-title"
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {account ? "编辑账号" : "添加账号"}
          <IconButton
            aria-label="关闭账号设置"
            onClick={() => void close()}
            disabled={Boolean(pending) && pending !== "官方授权"}
            size="small"
          >
            <CloseRounded fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ maxHeight: "min(65vh, 620px)" }}>
          <Stack spacing={2.2}>
            {!account && (
              <ToggleButtonGroup
                exclusive
                fullWidth
                size="small"
                value={kind}
                onChange={(_, value) => {
                  if (value) {
                    setKind(value);
                    setError("");
                  }
                }}
                disabled={locked}
                aria-label="账号登录方式"
              >
                <ToggleButton value="official">OpenAI 官方账号</ToggleButton>
                <ToggleButton value="custom">兼容渠道</ToggleButton>
              </ToggleButtonGroup>
            )}
            {kind === "official" ? (
              <>
                <Alert severity="info">
                  使用 ChatGPT 设备码授权，凭据独立保存在本机。
                  {account
                    ? "重新登录会添加新的账号档案。"
                    : "添加后可在账号列表切换。"}
                </Alert>
                <TextField
                  label="账号名称（可选）"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={locked}
                  placeholder="默认使用官方邮箱"
                  autoFocus
                />
                {login ? (
                  <Box
                    sx={{
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 2,
                      p: 2,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="body2" color="textSecondary">
                      在已打开的官方页面输入设备验证码
                    </Typography>
                    <Typography
                      sx={{
                        fontFamily: "monospace",
                        fontSize: 28,
                        letterSpacing: ".12em",
                        my: 1,
                      }}
                    >
                      {login.user_code}
                    </Typography>
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ justifyContent: "center", alignItems: "center" }}
                    >
                      <Button
                        size="small"
                        startIcon={<ContentCopyRounded />}
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(
                              login.user_code,
                            );
                            notify("验证码已复制");
                          } catch {
                            notify("复制失败，请手动选择验证码复制", true);
                          }
                        }}
                      >
                        复制验证码
                      </Button>
                      <Link
                        href={login.verification_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        variant="body2"
                      >
                        重新打开授权页
                      </Link>
                    </Stack>
                    <Typography
                      variant="caption"
                      color="textSecondary"
                      component="p"
                      sx={{ mt: 1 }}
                    >
                      等待完成授权，将自动添加账号…
                    </Typography>
                  </Box>
                ) : (
                  <Typography color="textSecondary" variant="body2">
                    点击“登录并添加”打开 OpenAI 官方授权页。
                  </Typography>
                )}
              </>
            ) : (
              <>
                <Accordion
                  expanded={importOpen}
                  onChange={(_, expanded) => setImportOpen(expanded)}
                  disableGutters
                  elevation={0}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: "8px !important",
                    "&:before": { display: "none" },
                  }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      已有配置？粘贴导入
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={1.5}>
                      <TextField
                        label="config.toml"
                        multiline
                        minRows={4}
                        maxRows={8}
                        value={configText}
                        onChange={(event) => setConfigText(event.target.value)}
                        disabled={locked}
                        slotProps={{ htmlInput: { spellCheck: false } }}
                      />
                      <TextField
                        label="auth.json 或 API Key（可选）"
                        multiline
                        minRows={2}
                        value={authText}
                        onChange={(event) => setAuthText(event.target.value)}
                        disabled={locked}
                        autoComplete="off"
                        slotProps={{ htmlInput: { spellCheck: false } }}
                      />
                      <Button
                        variant="outlined"
                        onClick={() => void parseConfig()}
                        disabled={locked || !configText.trim()}
                      >
                        识别并填入
                      </Button>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
                {importNotice && <Alert severity="info">{importNotice}</Alert>}
                <TextField
                  label="账号名称"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  disabled={locked}
                  error={Boolean(invalid.name)}
                  helperText={
                    invalid.name || "仅用于区分账号，Provider 统一为 MaoLocal"
                  }
                />
                <TextField
                  label="服务地址（Base URL）"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  required
                  disabled={locked}
                  error={Boolean(invalid.baseUrl)}
                  helperText={invalid.baseUrl}
                  placeholder="https://api.example.com/v1"
                />
                <TextField
                  label="API Key"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                  required={!account?.has_api_key}
                  disabled={locked}
                  error={Boolean(invalid.key)}
                  helperText={
                    invalid.key ||
                    (account?.has_api_key ? "留空保留已保存的 Key" : undefined)
                  }
                  type="password"
                  autoComplete="new-password"
                />
                <Autocomplete
                  freeSolo
                  options={models}
                  value={model}
                  inputValue={model}
                  onInputChange={(_, value) => setModel(value)}
                  disabled={locked}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="验证模型（可选）"
                      error={Boolean(invalid.model)}
                      helperText={
                        invalid.model ||
                        (model === "codex-auto-review"
                          ? "请确认渠道支持此模型用于普通对话；切换账号不更改当前模型"
                          : "仅用于验证连接；切换账号不更改当前模型")
                      }
                    />
                  )}
                />
                <Accordion
                  disableGutters
                  elevation={0}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: "8px !important",
                    "&:before": { display: "none" },
                  }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      高级连接设置
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={1.7}>
                      <TextField
                        label="模型目录地址（可选）"
                        value={catalog}
                        onChange={(event) => setCatalog(event.target.value)}
                        disabled={locked}
                        placeholder="http://localhost:8317/v1/models"
                        helperText="CPA 可填写服务地址下的 /models；无需添加 client_version，Codex 会自动附加。地址须提供完整 Codex 模型目录。"
                      />
                      <TextField
                        select
                        label="推理强度"
                        value={effort}
                        onChange={(event) => setEffort(event.target.value)}
                        disabled={locked}
                      >
                        {["low", "medium", "high", "xhigh", "max", "ultra"].map(
                          (value) => (
                            <MenuItem key={value} value={value}>
                              {value}
                            </MenuItem>
                          ),
                        )}
                      </TextField>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={discovery}
                            onChange={(_, value) => setDiscovery(value)}
                            disabled={locked}
                          />
                        }
                        label="启用渠道模型目录"
                      />
                      <Typography variant="caption" color="textSecondary">
                        开启并填写目录地址后，Codex 从渠道更新模型列表和推理选项。
                        关闭时保留账号中的地址，但不应用目录地址，使用 Codex 内置目录。
                        保存后需应用账号设置并重启 Codex。
                      </Typography>
                      {discovery && !catalog.trim() && (
                        <Alert severity="info">API Key 渠道需填写模型目录地址才能发现远程模型。</Alert>
                      )}
                      <FormControlLabel
                        control={
                          <Switch
                            checked={requiresAuth}
                            onChange={(_, value) => setRequiresAuth(value)}
                            disabled={locked}
                          />
                        }
                        label="使用 Codex 登录凭据（requires_openai_auth）"
                      />
                      <Typography variant="caption" color="textSecondary">
                        按渠道要求配置；开启登录凭据不代表该服务属于
                        OpenAI。目录请求会携带此渠道的认证信息，请使用渠道提供的目录地址。
                        普通编辑会保留已有隐藏连接参数。
                      </Typography>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ flexWrap: "wrap" }}
                  useFlexGap
                >
                  <Button
                    variant="outlined"
                    onClick={() => void verify(false)}
                    disabled={locked}
                  >
                    读取模型列表
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => void verify(true)}
                    disabled={locked}
                  >
                    验证连接
                  </Button>
                </Stack>
                <Typography variant="caption" color="textSecondary">
                  验证连接会发送一次
                  hi，可能消耗少量额度；读取模型列表只检测目录。两者都不会保存或切换账号。
                </Typography>
              </>
            )}
            {notice && (
              <Alert severity="success" sx={{ overflowWrap: "anywhere" }}>
                {notice}
              </Alert>
            )}
            {error && (
              <Alert severity="error" sx={{ overflowWrap: "anywhere" }}>
                {error}
              </Alert>
            )}
            {pending && (
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center" }}
                role="status"
              >
                <CircularProgress size={15} />
                <Typography variant="body2">{pending}…</Typography>
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => void close()}
            disabled={Boolean(pending) && pending !== "官方授权"}
          >
            {login ? "取消授权" : "取消"}
          </Button>
          <Button type="submit" variant="contained" disabled={locked}>
            {kind === "official" ? "登录并添加" : "保存账号"}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  );
}
