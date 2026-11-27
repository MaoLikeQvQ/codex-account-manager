import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  CssBaseline,
  Paper,
  Snackbar,
  Stack,
  ThemeProvider,
  Typography,
} from "@mui/material";
import { makeTheme } from "../shared/theme";
import { errorText, request } from "../shared/api/client";
import { useManager } from "./useManager";
import { UsageSummary } from "../features/overview/UsageSummary";
import { UsagePage } from "../features/usage/UsagePage";
import { panelStyle } from "../shared/ui/panelStyles";
import AccountsPanel from "../features/accounts/AccountsPanel";
import ToolsPanel from "../features/tools/ToolsPanel";
import RequestsPanel from "../features/requests/RequestsPanel";
import WorkspaceShell from "./WorkspaceShell";
import OverviewPage from "../features/overview/OverviewPage";
import UsagePeriodTabs from "../shared/usage/UsagePeriodTabs";
import { useRequests } from "../features/requests/useRequests";

function initialDark() {
  try {
    return localStorage.getItem("maox-theme") === "dark";
  } catch {
    return false;
  }
}

export default function App() {
  const [dark, setDark] = useState(initialDark);
  const [tab, setTab] = useState(4);
  const [accountModal, setAccountModal] = useState(false);
  const [toolModal, setToolModal] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [syncingPrices, setSyncingPrices] = useState(false);
  const [priceRevision, setPriceRevision] = useState(0);
  const [toast, setToast] = useState<{
    message: string;
    severity: "success" | "error" | "warning";
  } | null>(null);
  const notify = useCallback(
    (message: string, error = false) =>
      setToast({ message, severity: error ? "error" : "success" }),
    []
  );
  const manager = useManager(
    accountModal || toolModal || launching,
    priceRevision
  );
  const theme = useMemo(() => makeTheme(dark), [dark]);
  const { state, active, api, busy, usage } = manager;
  const requests = useRequests(
    active,
    manager.period,
    manager.date,
    accountModal || toolModal || launching || busy || tab === 3,
    priceRevision
  );
  const realtimeRequests = useRequests(
    active,
    "today",
    "",
    accountModal || toolModal || launching || busy || tab !== 3,
    priceRevision
  );
  const shownHistory = useRef<string | null>(null);
  const claim = state?.history_claim;
  const claimKey = claim
    ? JSON.stringify([claim.account, claim.status, claim.failed])
    : null;
  useEffect(() => {
    if (!claimKey) {
      shownHistory.current = null;
      return;
    }
    // Let an explicit operation message finish before showing the background reminder.
    if (toast || shownHistory.current === claimKey || !claim) return;
    shownHistory.current = claimKey;
    const title =
      claim.status === "pending" ? "历史归属待完成" : "历史归属未完成";
    setToast({
      severity: "warning",
      message: `${title}：${claim.account}${
        claim.failed ? `（${claim.failed} 个会话失败）` : ""
      }。下次切换账号或启动 Codex 时自动重试。`,
    });
  }, [claimKey, claim, toast]);
  function toggleTheme() {
    setDark((previous) => {
      try {
        localStorage.setItem("maox-theme", previous ? "light" : "dark");
      } catch {
        /* Theme remains usable without storage. */
      }
      return !previous;
    });
  }
  async function launch() {
    if (launching || busy || !active) return;
    setLaunching(true);
    try {
      const response = await api("/api/codex/launch", { restart: true });
      notify(response.message || "Codex 已启动", response.warning);
    } catch (failure) {
      notify(errorText(failure), true);
    } finally {
      setLaunching(false);
    }
  }
  async function syncModelPrices() {
    if (syncingPrices) return;
    setSyncingPrices(true);
    try {
      const response = await request("/api/pricing/sync", {});
      setPriceRevision((previous) => previous + 1);
      notify(response.message || "模型价格已同步");
    } catch (failure) {
      notify(errorText(failure), true);
    } finally {
      setSyncingPrices(false);
    }
  }
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      <WorkspaceShell
        tab={tab}
        onTab={setTab}
        dark={dark}
        toggleTheme={toggleTheme}
        refresh={() => void manager.refreshState()}
        launch={() => void launch()}
        launching={launching}
        busy={busy}
        active={active}
        state={state}
        error={manager.error}
        updatedAt={manager.updatedAt}
      >
        {manager.error && (
          <Alert
            severity="error"
            action={
              <Button onClick={() => void manager.refreshState()}>重试</Button>
            }
            sx={{ mb: 2 }}
          >
            无法读取配置：{manager.error}
          </Alert>
        )}
        <Box
          role="tabpanel"
          id="workspace-panel-4"
          aria-label="总览"
          hidden={tab !== 4}
          sx={{ display: tab === 4 ? "block" : "none" }}
        >
          {tab === 4 && !state && !manager.error && (
            <Stack
              spacing={1}
              sx={{ alignItems: "center", py: 9 }}
              role="status"
            >
              <CircularProgress size={25} />
              <Typography variant="body2" color="textSecondary">
                正在读取配置…
              </Typography>
            </Stack>
          )}
          {tab === 4 && state && (
            <OverviewPage
              active={active}
              state={state}
              quota={manager.quota}
              quotaLoading={manager.quotaLoading}
              refreshQuota={() => void manager.refreshQuota()}
              usage={usage}
              feed={requests.feed}
              usageError={manager.usageError}
              requestError={requests.error}
              period={manager.period}
              onNavigate={setTab}
            />
          )}
        </Box>
        {tab === 0 && (
          <>
            <UsagePeriodTabs
              period={manager.period}
              setPeriod={manager.setPeriod}
              date={manager.date}
              setDate={manager.setDate}
            />
            <UsageSummary usage={usage} feed={requests.feed} />
          </>
        )}
        <Paper
          sx={{
            ...(tab === 0 || tab === 3 ? panelStyle : {}),
            bgcolor:
              tab === 1 || tab === 2 ? "transparent" : "background.paper",
            mt: tab === 0 ? 1.25 : 0,
            overflow: "hidden",
            flex: { sm: tab === 3 ? "1 1 0" : "0 1 auto" },
            flexShrink: tab === 0 || tab === 3 ? 1 : 0,
            minHeight: { xs: tab === 4 ? 0 : "auto", sm: 0 },
            display: tab === 4 ? "none" : "flex",
            flexDirection: "column",
          }}
        >
          {!state && !manager.error ? (
            <Stack spacing={1} sx={{ alignItems: "center", py: 9 }}>
              <CircularProgress size={25} />
              <Typography variant="body2" color="textSecondary">
                正在读取配置…
              </Typography>
            </Stack>
          ) : (
            <>
              <Box
                role="tabpanel"
                id="workspace-panel-3"
                aria-labelledby="workspace-tab-3"
                hidden={tab !== 3}
                sx={{
                  display: tab === 3 ? "flex" : "none",
                  flexDirection: "column",
                  flex: 1,
                  minHeight: 0,
                  overflow: "auto",
                }}
              >
                <RequestsPanel
                  feed={realtimeRequests.feed}
                  error={realtimeRequests.error}
                  loading={realtimeRequests.loading}
                  refresh={() => void realtimeRequests.refresh()}
                  active={active}
                />
              </Box>
              <Box
                role="tabpanel"
                id="workspace-panel-0"
                aria-labelledby="workspace-tab-0"
                hidden={tab !== 0}
                sx={{
                  display: tab === 0 ? "flex" : "none",
                  flexDirection: "column",
                  flex: 1,
                  minHeight: 0,
                  overflow: "auto",
                }}
              >
                <UsagePage
                  period={manager.period}
                  usage={usage}
                  error={manager.usageError}
                  loading={manager.usageLoading}
                  refresh={() => void manager.refreshUsage()}
                  syncPrices={() => void syncModelPrices()}
                  syncingPrices={syncingPrices}
                  active={active}
                  onAccounts={() => setTab(1)}
                />
              </Box>
              {state && (
                <Box
                  role="tabpanel"
                  id="workspace-panel-1"
                  aria-labelledby="workspace-tab-1"
                  hidden={tab !== 1}
                  sx={{
                    display: tab === 1 ? "flex" : "none",
                    flexDirection: "column",
                    flex: 1,
                    minHeight: 0,
                    overflow: "auto",
                  }}
                >
                  <AccountsPanel
                    state={state}
                    api={api}
                    notify={notify}
                    busy={busy}
                    onModalChange={setAccountModal}
                    onQuota={manager.acceptQuota}
                  />
                </Box>
              )}
              {state && (
                <Box
                  role="tabpanel"
                  id="workspace-panel-2"
                  aria-labelledby="workspace-tab-2"
                  hidden={tab !== 2}
                  sx={{
                    display: tab === 2 ? "flex" : "none",
                    flexDirection: "column",
                    flex: 1,
                    minHeight: 0,
                    overflow: "auto",
                  }}
                >
                  <ToolsPanel
                    state={state}
                    api={api}
                    notify={notify}
                    busy={busy}
                    onModalChange={setToolModal}
                  />
                </Box>
              )}
            </>
          )}
        </Paper>
      </WorkspaceShell>
      <Snackbar
        open={!!toast}
        autoHideDuration={2000}
        key={toast?.message}
        onClose={(_, reason) => {
          if (reason !== "clickaway") setToast(null);
        }}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        sx={{
          top: { xs: 16, sm: 20 },
          maxWidth: "calc(100% - 32px)",
          width: "max-content",
        }}
      >
        <Alert
          severity={toast?.severity ?? "success"}
          variant="standard"
          onClose={() => setToast(null)}
          sx={{
            maxWidth: 640,
            whiteSpace: "pre-wrap",
            border: "1px solid",
            borderColor: `${toast?.severity ?? "success"}.light`,
            boxShadow: 2,
            borderRadius: 1.5,
            alignItems: "center",
          }}
        >
          {toast?.message}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  );
}
