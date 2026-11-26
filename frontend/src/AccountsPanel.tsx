import Dialog from "./ManagerDialog";
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddRounded from "@mui/icons-material/AddRounded";
import CloseRounded from "@mui/icons-material/CloseRounded";
import SearchRounded from "@mui/icons-material/SearchRounded";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import AccountCard from "./AccountCard";
import AccountDialog from "./AccountDialog";
import WakeupDialog from "./WakeupDialog";
import ScheduleRounded from "@mui/icons-material/ScheduleRounded";
import AccountQuota from "./AccountQuota";
import { errorText } from "./api";
import type { Account, AppState, Notify, Quota, RequestApi } from "./types";

interface Props {
  state: AppState;
  api: RequestApi;
  notify: Notify;
  busy: boolean;
  onModalChange: (open: boolean) => void;
  onQuota?: (name: string, quota: Quota, expectedVersion?: string) => void;
}
const accountType = (account: Account) =>
  account.account_type === "official"
    ? "OpenAI 官方"
    : account.connection_type === "sub2api"
    ? "Sub2API · MaoLocal"
    : "兼容渠道 · MaoLocal";

export default function AccountsPanel({
  state,
  api,
  notify,
  busy,
  onModalChange,
  onQuota,
}: Props) {
  const [wakeupOpen, setWakeupOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState<{ account: Account | null } | null>(
    null
  );
  const [deleting, setDeleting] = useState<Account | null>(null);
  const [pending, setPending] = useState("");
  const [detailNotice, setDetailNotice] = useState("");
  const [detailError, setDetailError] = useState("");
  const [quotas, setQuotas] = useState<Record<string, Quota>>({});
  const [quotaLoading, setQuotaLoading] = useState<Record<string, boolean>>({});
  const quotaPending = useRef(new Set<string>());
  const modalCallback = useRef(onModalChange);
  modalCallback.current = onModalChange;
  const detail = state.accounts.find((item) => item.name === selected);
  const locked = busy || Boolean(pending);
  const openModal = Boolean(
    detail || editing || deleting || pending || wakeupOpen
  );

  useEffect(() => {
    modalCallback.current(openModal);
  }, [openModal]);
  useEffect(() => () => modalCallback.current(false), []);

  async function refreshQuota(account: Account) {
    if (
      account.account_type !== "official" ||
      quotaPending.current.has(account.name)
    )
      return;
    const name = account.name;
    quotaPending.current.add(name);
    setQuotaLoading((previous) => ({ ...previous, [name]: true }));
    try {
      const response = await api<Quota>(
        `/api/accounts/quota?name=${encodeURIComponent(name)}`
      );
      if (!response.result) throw new Error("官方暂未返回额度数据");
      setQuotas((previous) => ({ ...previous, [name]: response.result! }));
      onQuota?.(name, response.result, account.updated_at);
    } catch (error) {
      const failed = {
        errors: { request: errorText(error) },
        fetched_at: new Date().toISOString(),
      };
      setQuotas((previous) => ({ ...previous, [name]: failed }));
      onQuota?.(name, failed, account.updated_at);
    } finally {
      quotaPending.current.delete(name);
      setQuotaLoading((previous) => ({ ...previous, [name]: false }));
    }
  }

  function showDetails(account: Account) {
    setSelected(account.name);
    setDetailNotice("");
    setDetailError("");
    if (account.account_type === "official" && !quotas[account.name])
      void refreshQuota(account);
  }

  async function action(
    account: Account,
    operation: "activate" | "verify-connection" | "delete"
  ) {
    if (locked) return;
    setPending(operation);
    setDetailNotice("");
    setDetailError("");
    try {
      const result = await api(
        `/api/accounts/${operation}`,
        operation === "verify-connection"
          ? { ...account, original_name: account.name }
          : { name: account.name }
      );
      const message = result.message || "操作完成";
      setDetailNotice(message);
      notify(message, result.warning);
      if (operation === "delete") {
        setDeleting(null);
        setSelected("");
        setEditing(null);
        setQuotas((previous) => {
          const next = { ...previous };
          delete next[account.name];
          return next;
        });
      }
    } catch (error) {
      setDetailError(errorText(error));
      notify(errorText(error), true);
    } finally {
      setPending("");
    }
  }

  const filtered = state.accounts.filter((account) =>
    `${account.name} ${account.email} ${account.base_url} ${account.default_model}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );
  return (
    <>
      {wakeupOpen && (
        <WakeupDialog
          api={api}
          defaultModel={state.current.model}
          officialCount={
            state.accounts.filter((item) => item.account_type === "official")
              .length
          }
          onClose={() => setWakeupOpen(false)}
        />
      )}
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        sx={{
          alignItems: { sm: "center" },
          justifyContent: "space-between",
          px: 0.5,
          pt: 0.5,
          pb: 1.25,
        }}
      >
        <Box>
          <Typography variant="caption" color="textSecondary">
            {state.accounts.length} 个账号 · 保存配置后，点击“使用”才会切换
          </Typography>
        </Box>
        <Stack
          direction="row"
          spacing={1}
          useFlexGap
          sx={{ flexWrap: "wrap", alignItems: "center" }}
        >
          <TextField
            size="small"
            placeholder="搜索账号"
            aria-label="搜索账号"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            sx={{ width: { xs: "100%", sm: 220 } }}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchRounded fontSize="small" />
                  </InputAdornment>
                ),
              },
              htmlInput: { "aria-label": "搜索账号" },
            }}
          />
          <Button
            startIcon={<ScheduleRounded />}
            onClick={() => setWakeupOpen(true)}
            disabled={locked}
            sx={{ flexShrink: 0 }}
          >
            定时唤醒
          </Button>
          <Button
            variant="contained"
            startIcon={<AddRounded />}
            onClick={() => setEditing({ account: null })}
            disabled={locked}
            sx={{ flexShrink: 0 }}
          >
            添加账号
          </Button>
        </Stack>
      </Stack>
      {detailError && !detail && !deleting && (
        <Alert severity="error" sx={{ mx: 2, mb: 1 }}>
          {detailError}
        </Alert>
      )}
      <Box
        role="list"
        aria-label="账号列表"
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            sm: "repeat(2, minmax(0, 1fr))",
          },
          alignItems: "start",
          gap: 1,
          px: 0,
          pb: 2.2,
        }}
      >
        {filtered.map((account) => (
          <AccountCard
            key={`${account.name}:${account.updated_at}`}
            account={account}
            quota={quotas[account.name]}
            restartRequired={state.codex.restart_required}
            locked={locked}
            api={api}
            onQuota={(quota) => {
              setQuotas((previous) => ({ ...previous, [account.name]: quota }));
              onQuota?.(account.name, quota, account.updated_at);
            }}
            onDetails={() => showDetails(account)}
            onActivate={() => void action(account, "activate")}
          />
        ))}
      </Box>
      {!filtered.length && (
        <Box
          sx={{
            textAlign: "center",
            py: 4,
            bgcolor: "background.paper",
            borderRadius: "16px",
          }}
        >
          <Typography sx={{ fontWeight: 600 }}>
            {state.accounts.length ? "没有匹配的账号" : "添加你的第一个账号"}
          </Typography>
          <Typography
            variant="body2"
            color="textSecondary"
            sx={{ mt: 0.6, mb: 2 }}
          >
            {state.accounts.length
              ? "试试账号名称、邮箱或服务地址。"
              : "连接 OpenAI 官方账号，或导入 Responses 兼容渠道。"}
          </Typography>
          {!state.accounts.length && (
            <Button
              variant="outlined"
              onClick={() => setEditing({ account: null })}
            >
              添加账号
            </Button>
          )}
        </Box>
      )}
      <Box
        sx={{
          px: 0.5,
          py: 1.3,
        }}
      >
        <Typography variant="caption" color="textSecondary">
          {filtered.length} / {state.accounts.length} 个账号 ·
          账号凭据仅保存在本机
        </Typography>
      </Box>

      <Dialog
        open={Boolean(detail) && !editing && !deleting}
        fullWidth
        maxWidth="sm"
        scroll="paper"
        onClose={() => {
          if (!locked) setSelected("");
        }}
        aria-labelledby="account-detail-title"
      >
        {detail && (
          <>
            <DialogTitle
              id="account-detail-title"
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  component="span"
                  variant="h6"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {detail.name}
                </Typography>
                <Typography
                  variant="caption"
                  color="textSecondary"
                  sx={{ display: "block" }}
                >
                  {accountType(detail)}
                </Typography>
              </Box>
              <IconButton
                size="small"
                aria-label="关闭账号详情"
                disabled={locked}
                onClick={() => setSelected("")}
              >
                <CloseRounded fontSize="small" />
              </IconButton>
            </DialogTitle>
            <DialogContent dividers sx={{ maxHeight: "65vh" }}>
              <Stack spacing={2}>
                <Box
                  sx={{
                    display: "grid",
                    gridTemplateColumns: "70px minmax(0, 1fr)",
                    gap: 1,
                    overflowWrap: "anywhere",
                  }}
                >
                  <Typography variant="body2" color="textSecondary">
                    连接
                  </Typography>
                  <Typography variant="body2">
                    {detail.email || detail.base_url || "OpenAI 官方"}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {detail.account_type === "official"
                      ? "模型目录"
                      : "验证模型"}
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                    {detail.account_type === "official"
                      ? "Codex 官方自动发现"
                      : detail.default_model || "未设置验证模型"}
                  </Typography>
                  {detail.account_type !== "official" && (
                    <>
                      <Typography variant="body2" color="textSecondary">
                        模型目录
                      </Typography>
                      <Typography variant="body2">
                        {detail.api_key_model_discovery &&
                        detail.model_catalog_url
                          ? `渠道目录：${detail.model_catalog_url}`
                          : detail.api_key_model_discovery
                          ? "渠道发现已开启，尚未配置目录地址"
                          : "Codex 内置目录"}
                      </Typography>
                    </>
                  )}
                  <Typography variant="body2" color="textSecondary">
                    状态
                  </Typography>
                  <Typography variant="body2">
                    {detail.active
                      ? detail.pending_apply
                        ? "当前账号有待应用修改"
                        : "当前使用"
                      : "尚未启用"}
                  </Typography>
                  {detail.plan_type && (
                    <>
                      <Typography variant="body2" color="textSecondary">
                        套餐
                      </Typography>
                      <Typography variant="body2">
                        {detail.plan_type.toUpperCase()}
                      </Typography>
                    </>
                  )}
                </Box>
                {detail.account_type === "official" && (
                  <>
                    <Divider />
                    <Stack
                      direction="row"
                      sx={{
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <Typography sx={{ fontWeight: 600 }} variant="body2">
                        额度与用量
                      </Typography>
                      <Button
                        size="small"
                        startIcon={
                          quotaLoading[detail.name] ? (
                            <CircularProgress size={13} />
                          ) : (
                            <RefreshRounded />
                          )
                        }
                        disabled={quotaLoading[detail.name] || locked}
                        onClick={() => void refreshQuota(detail)}
                      >
                        刷新额度
                      </Button>
                    </Stack>
                    <AccountQuota
                      account={detail}
                      quota={quotas[detail.name]}
                    />
                  </>
                )}
                {detailNotice && (
                  <Alert severity="success" sx={{ overflowWrap: "anywhere" }}>
                    {detailNotice}
                  </Alert>
                )}
                {detailError && <Alert severity="error">{detailError}</Alert>}
                {pending && (
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: "center" }}
                    role="status"
                  >
                    <CircularProgress size={15} />
                    <Typography variant="body2">正在处理，请稍候…</Typography>
                  </Stack>
                )}
              </Stack>
            </DialogContent>
            <DialogActions sx={{ flexWrap: "wrap", gap: 0.5 }}>
              <Button
                color="error"
                onClick={() => setDeleting(detail)}
                disabled={locked}
              >
                移除账号
              </Button>
              <Box sx={{ flex: 1 }} />
              {detail.account_type !== "official" && (
                <Button
                  onClick={() => void action(detail, "verify-connection")}
                  disabled={locked}
                  title="发送 hi，可能消耗少量额度"
                >
                  验证连接
                </Button>
              )}
              <Button
                onClick={() => setEditing({ account: detail })}
                disabled={locked}
              >
                {detail.account_type === "official" ? "管理授权" : "编辑"}
              </Button>
              <Button
                variant="contained"
                disabled={locked || (detail.active && !detail.pending_apply)}
                onClick={() => void action(detail, "activate")}
              >
                {detail.active
                  ? detail.pending_apply
                    ? "应用修改"
                    : "使用中"
                  : "使用此账号"}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      {editing && (
        <AccountDialog
          key={editing.account?.name || "new"}
          account={editing.account}
          api={api}
          notify={notify}
          disabled={locked}
          onClose={() => setEditing(null)}
        />
      )}
      <Dialog
        open={Boolean(deleting)}
        onClose={() => {
          if (!locked) setDeleting(null);
        }}
        maxWidth="xs"
        fullWidth
        aria-labelledby="delete-account-title"
      >
        <DialogTitle id="delete-account-title">移除账号</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
            将“{deleting?.name}
            ”从管理器列表移除，并删除管理器保存的账号档案。Codex
            当前配置与登录状态保持不变，不会注销账号、取消订阅或删除对话。
          </Typography>
          {detailError && (
            <Alert severity="error" sx={{ mt: 1.5 }}>
              {detailError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting(null)} disabled={locked} autoFocus>
            取消
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={locked}
            onClick={() => deleting && void action(deleting, "delete")}
          >
            {pending ? "正在移除…" : "确认移除"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
