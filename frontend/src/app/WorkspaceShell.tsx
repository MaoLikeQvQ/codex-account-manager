import type { ReactNode } from "react";
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Tooltip,
  Typography,
  useMediaQuery,
} from "@mui/material";
import DashboardRounded from "@mui/icons-material/DashboardRounded";
import PeopleOutlineRounded from "@mui/icons-material/PeopleOutlineRounded";
import BarChartRounded from "@mui/icons-material/BarChartRounded";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import SwapVertRounded from "@mui/icons-material/SwapVertRounded";
import DarkModeOutlined from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlined from "@mui/icons-material/LightModeOutlined";
import RefreshRounded from "@mui/icons-material/RefreshRounded";
import OpenInNewRounded from "@mui/icons-material/OpenInNewRounded";
import RestartAltRounded from "@mui/icons-material/RestartAltRounded";
import appIcon from "../../../assets/maox-icon.svg";
import type { Account, AppState } from "../shared/types";

const pages = [
  { value: 4, label: "总览", icon: <DashboardRounded /> },
  { value: 1, label: "账号管理", icon: <PeopleOutlineRounded /> },
  { value: 0, label: "用量明细", icon: <BarChartRounded /> },
  { value: 3, label: "实时请求", icon: <SwapVertRounded /> },
  { value: 2, label: "工具设置", icon: <SettingsOutlined /> },
];

interface Props {
  children: ReactNode;
  tab: number;
  onTab: (tab: number) => void;
  active?: Account;
  state: AppState | null;
  dark: boolean;
  toggleTheme: () => void;
  refresh: () => void;
  launch: () => void;
  launching: boolean;
  busy: boolean;
  error: string;
  updatedAt: Date | null;
}

export default function WorkspaceShell({
  children,
  tab,
  onTab,
  dark,
  toggleTheme,
  refresh,
  launch,
  launching,
  busy,
  active,
  state,
  error,
  updatedAt,
}: Props) {
  const compact = useMediaQuery("(max-width:599px)");
  const status = state?.codex.restart_required
    ? "待重启 Codex"
    : state?.codex.running
    ? "Codex 运行中"
    : "Codex 未运行";
  return (
    <Box
      sx={{
        height: "100dvh",
        minHeight: 0,
        display: "flex",
        flexDirection: { xs: "column", sm: "row" },
        bgcolor: "background.default",
      }}
    >
      <Box
        component="aside"
        sx={{
          width: { sm: 180, md: 196 },
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          px: 1.5,
          pt: { xs: 1.5, sm: 4 },
          pb: { sm: 2 },
          bgcolor: dark ? "#1c1e25" : "#e7e8eb",
          borderRight: 0,
          borderBottom: { xs: "1px solid", sm: 0 },
          borderColor: "divider",
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: "center", px: 1, mb: { xs: 1.5, sm: 2.75 } }}
        >
          <Box
            component="img"
            src={appIcon}
            alt=""
            sx={{ width: 31, height: 31 }}
          />
          <Typography
            sx={{ fontSize: 16, fontWeight: 700, letterSpacing: "-.4px" }}
          >
            MaoX
          </Typography>
          <Typography
            variant="caption"
            color="textSecondary"
            sx={{ display: { xs: "block", sm: "none" } }}
          >
            Codex 账号管理器
          </Typography>
        </Stack>
        <Box component="nav" aria-label="主导航" sx={{ minWidth: 0 }}>
          <Tabs
            value={tab}
            onChange={(_, value: number) => onTab(value)}
            orientation={compact ? "horizontal" : "vertical"}
            variant="scrollable"
            scrollButtons={compact ? "auto" : false}
            aria-label="工作区"
            sx={{ minHeight: 40, "& .MuiTabs-list": { gap: 0.5 } }}
          >
            {pages.map((page) => (
              <Tab
                key={page.value}
                value={page.value}
                id={"workspace-tab-" + page.value}
                label={page.label}
                icon={compact ? undefined : page.icon}
                iconPosition="start"
                aria-controls={"workspace-panel-" + page.value}
                sx={{
                  justifyContent: "flex-start",
                  textAlign: "left",
                  px: 1.5,
                  minHeight: 40,
                  mr: 0,
                  border: 0,
                  borderRadius: "9px",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "text.secondary",
                  bgcolor: "transparent",
                  "& .MuiSvgIcon-root": { fontSize: 19, mr: 1.5 },
                  "&.Mui-selected": {
                    color: "primary.main",
                    bgcolor: "action.selected",
                    fontWeight: 650,
                  },
                }}
              />
            ))}
          </Tabs>
        </Box>
        <Box sx={{ flex: 1, display: { xs: "none", sm: "block" } }} />
        <Box
          sx={{
            display: { xs: "none", sm: "block" },
            px: 1.25,
            pb: 1.5,
            pt: 3,
          }}
        >
          <Stack
            direction="row"
            spacing={0.8}
            sx={{ alignItems: "center", mb: 0.5 }}
          >
            <Box
              sx={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                bgcolor: error
                  ? "error.main"
                  : state?.codex.restart_required
                  ? "warning.main"
                  : state?.codex.running
                  ? "success.main"
                  : "text.disabled",
              }}
            />
            <Typography variant="caption" color="textSecondary">
              {error ? "连接异常" : status}
            </Typography>
          </Stack>
          <Typography
            variant="caption"
            color="textSecondary"
            noWrap
            component="div"
            title={active?.name}
          >
            {active?.name || "未启用账号"}
          </Typography>
        </Box>
        <Button
          onClick={launch}
          disabled={!active || busy || launching}
          startIcon={
            launching ? (
              <CircularProgress size={15} />
            ) : state?.codex.running ? (
              <RestartAltRounded />
            ) : (
              <OpenInNewRounded />
            )
          }
          sx={{
            display: { xs: "none", sm: "inline-flex" },
            color: "text.primary",
            justifyContent: "flex-start",
            px: 1.5,
            minHeight: 40,
          }}
        >
          {launching
            ? "启动中…"
            : state?.codex.running
            ? "重启 Codex"
            : "启动 Codex"}
        </Button>
      </Box>
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box
          component="header"
          sx={{
            minHeight: { xs: 52, sm: 56 },
            px: { xs: 2, md: 2 },
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            flexShrink: 0,
          }}
        >
          <Typography component="h1" variant="h5">
            {pages.find((page) => page.value === tab)?.label}
          </Typography>
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <Typography
              variant="caption"
              color="textSecondary"
              sx={{ mr: 1, display: { xs: "none", md: "block" } }}
            >
              {error
                ? "连接异常"
                : updatedAt
                ? "更新于 " +
                  updatedAt.toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "正在连接…"}
            </Typography>
            <Tooltip title="刷新账号状态">
              <IconButton
                aria-label="刷新账号状态"
                disabled={busy}
                onClick={refresh}
              >
                <RefreshRounded sx={{ fontSize: 19 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title={dark ? "切换浅色" : "切换深色"}>
              <IconButton
                aria-label={dark ? "切换浅色" : "切换深色"}
                onClick={toggleTheme}
              >
                {dark ? (
                  <LightModeOutlined sx={{ fontSize: 18 }} />
                ) : (
                  <DarkModeOutlined sx={{ fontSize: 18 }} />
                )}
              </IconButton>
            </Tooltip>
            <Tooltip title={state?.codex.running ? "重启 Codex" : "启动 Codex"}>
              <IconButton
                aria-label={state?.codex.running ? "重启 Codex" : "启动 Codex"}
                disabled={!active || busy || launching}
                onClick={launch}
                sx={{ display: { sm: "none" } }}
              >
                {launching ? (
                  <CircularProgress size={16} />
                ) : (
                  <OpenInNewRounded fontSize="small" />
                )}
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>
        <Box
          component="main"
          sx={{
            px: { xs: 1.5, md: 2 },
            pb: { xs: 1.5, md: 2 },
            flex: 1,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
}
