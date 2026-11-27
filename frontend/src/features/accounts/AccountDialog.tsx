import Dialog from "../../shared/ui/ManagerDialog";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import CloseRounded from "@mui/icons-material/CloseRounded";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import ContentCopyRounded from "@mui/icons-material/ContentCopyRounded";
import { errorText } from "../../shared/api/client";
import type { Account, Notify, RequestApi } from "../../shared/types";

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
  const [importOpen, setImportOpen] = useState(false);
  const [importNotice, setImportNotice] = useState("");
  const [pending, setPending] = useState("");
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

  function defaultName() {
    try {
      return new URL(baseUrl.trim()).host;
    } catch {
      return "";
    }
  }

  function payload() {
    const originalCatalog = provider
      ? String(provider.model_catalog_url ?? "")
      : account?.model_catalog_url ?? "";
    // Keep the saved discovery flag unless the catalog address actually changes.
    const catalogChanged = catalog.trim() !== originalCatalog.trim();
    return {
      original_name: account?.name ?? "",
      name: name.trim() || defaultName(),
      provider_name: name.trim() || defaultName(),
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
      api_key_model_discovery: catalogChanged ? Boolean(catalog.trim()) : discovery,
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

  function validate() {
    const failures: Record<string, string> = {};
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
        `已识别 ${parsed.provider_id}，应用时沿用当前 Provider。${parsed.ignored_fields.length ? `未导入字段：${parsed.ignored_fields.join("、")}。` : ""}请检查后保存。`,
      );
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
      maxWidth="xs"
      slotProps={{
        paper: {
          "aria-labelledby": "account-dialog-title",
          sx: {
            width: 480,
            maxWidth: "calc(100% - 32px)",
            m: 2,
            maxHeight: "calc(100% - 32px)",
            borderRadius: "12px",
            "& .MuiButton-root": { minHeight: 28, px: 1.25, py: 0.4 },
            "& .MuiIconButton-root": { p: 0.5 },
            "& .MuiInputBase-root": { fontSize: 12 },
            "& .MuiInputLabel-root": { fontSize: 12 },
            "& .MuiAccordionSummary-root": { minHeight: 34, px: 1.25 },
            "& .MuiAccordionSummary-content": { my: 0.75 },
            "& .MuiAccordionDetails-root": { px: 1.25, pt: 0, pb: 1.25 },
          },
        },
      }}
      onClose={() => void close()}
      aria-labelledby="account-dialog-title"
      scroll="paper"
    >
      <Box
        component="form"
        noValidate
        onSubmit={submit}
        sx={{ display: "flex", flexDirection: "column", minHeight: 0, maxHeight: "100%" }}
      >
        <DialogTitle
          id="account-dialog-header"
          component="div"
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 2, py: 1.25, fontSize: 15, flexShrink: 0,
          }}
        >
          <Typography component="h2" variant="inherit" id="account-dialog-title">
            {account ? "编辑账号" : "添加账号"}
          </Typography>
          <IconButton
            aria-label="关闭账号设置"
            onClick={() => void close()}
            disabled={Boolean(pending) && pending !== "官方授权"}
            size="small"
          >
            <CloseRounded fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 2, minHeight: 0 }}>
          <Stack spacing={1.5}>
            {!account && (
              <ToggleButtonGroup
                exclusive
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
                sx={{
                  alignSelf: "flex-start",
                  "& .MuiToggleButton-root": { px: 1.5, py: 0.5, fontSize: 12 },
                }}
              >
                <ToggleButton value="official">OpenAI 官方账号</ToggleButton>
                <ToggleButton value="custom">兼容渠道</ToggleButton>
              </ToggleButtonGroup>
            )}
            {kind === "official" ? (
              <>
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
                    通过 OpenAI 官方页面授权，凭据保存在本机。
                  </Typography>
                )}
              </>
            ) : (
              <>
                <TextField
                  label="服务地址（Base URL）"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  required
                  disabled={locked}
                  error={Boolean(invalid.baseUrl)}
                  helperText={invalid.baseUrl}
                  placeholder="https://api.example.com/v1"
                  autoComplete="off"
                  slotProps={{ htmlInput: { spellCheck: false } }}
                />
                <TextField
                  label="API Key"
                  value={key}
                  onChange={(event) => setKey(event.target.value)}
                  required={!account?.has_api_key}
                  disabled={locked}
                  error={Boolean(invalid.key)}
                  helperText={invalid.key}
                  placeholder={
                    account?.has_api_key
                      ? "留空保留已保存的 Key"
                      : "输入渠道提供的 API Key"
                  }
                  type="password"
                  autoComplete="new-password"
                />
                <TextField
                  label="模型目录地址（可选）"
                  value={catalog}
                  onChange={(event) => setCatalog(event.target.value)}
                  disabled={locked}
                  placeholder="https://api.example.com/v1/models"
                  autoComplete="off"
                  slotProps={{ htmlInput: { spellCheck: false } }}
                />
                <TextField
                  label="账号名称（可选）"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={locked}
                  placeholder={defaultName() || "默认使用服务域名"}
                />
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
                        minRows={3}
                        maxRows={5}
                        value={configText}
                        onChange={(event) => setConfigText(event.target.value)}
                        disabled={locked}
                        slotProps={{ htmlInput: { spellCheck: false } }}
                      />
                      <TextField
                        label="auth.json 或 API Key（可选）"
                        multiline
                        minRows={1}
                        maxRows={3}
                        value={authText}
                        onChange={(event) => setAuthText(event.target.value)}
                        disabled={locked}
                        autoComplete="off"
                        slotProps={{ htmlInput: { spellCheck: false } }}
                      />
                      <Button
                        variant="outlined"
                        sx={{ alignSelf: "flex-end" }}
                        onClick={() => void parseConfig()}
                        disabled={locked || !configText.trim()}
                      >
                        识别并填入
                      </Button>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
                {importNotice && <Alert severity="info">{importNotice}</Alert>}
              </>
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
        <DialogActions sx={{ px: 2, py: 1.25, gap: 0.5, flexShrink: 0 }}>
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
