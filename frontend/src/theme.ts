import { alpha, createTheme } from "@mui/material/styles";

export const mono =
  '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace';

export function tpsColor(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "text.secondary";
  const displayed = Number(value.toFixed(1));
  return displayed < 10
    ? "error.main"
    : displayed < 30
      ? "warning.main"
      : "success.main";
}

export function elapsedTimeColor(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value) || value < 0)
    return "text.secondary";
  const displayed = Number(value.toFixed(2));
  return displayed < 10
    ? "success.main"
    : displayed < 20
      ? "warning.main"
      : "error.main";
}

export function makeTheme(dark: boolean) {
  const accent = dark ? "#70acff" : "#0866ed";
  const divider = dark ? "#30343f" : "#edeef2";
  const paper = dark ? "#1b1e26" : "#ffffff";
  const text = dark ? "#edf0f6" : "#303238";
  const secondary = dark ? "#a3adbf" : "#7a7d86";
  return createTheme({
    palette: {
      mode: dark ? "dark" : "light",
      primary: { main: accent, contrastText: dark ? "#101827" : "#ffffff" },
      secondary: { main: secondary },
      success: { main: dark ? "#4dcc83" : "#16833a" },
      info: { main: accent },
      warning: { main: dark ? "#edba68" : "#9a6700" },
      error: { main: dark ? "#fa9292" : "#c73838" },
      background: { default: dark ? "#121419" : "#f5f6f9", paper },
      text: {
        primary: text,
        secondary,
        disabled: dark ? "#788498" : "#8b95a5",
      },
      divider,
      action: {
        active: secondary,
        hover: alpha(accent, dark ? 0.08 : 0.045),
        selected: alpha(accent, dark ? 0.15 : 0.09),
        disabled: dark ? "#788498" : "#8b95a5",
        disabledBackground: dark ? "#262e3a" : "#eef1f5",
      },
    },
    typography: {
      fontFamily:
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: 13,
      h5: { fontSize: 23, fontWeight: 700, letterSpacing: "-.4px" },
      h6: { fontSize: 16, fontWeight: 650 },
      subtitle2: { fontSize: 13, fontWeight: 600 },
      body2: { fontSize: 13, lineHeight: 1.7 },
      button: { textTransform: "none", fontWeight: 550, fontSize: 12 },
      caption: { fontSize: 11, lineHeight: 1.65 },
    },
    shape: { borderRadius: 14 },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            margin: 0,
            minWidth: 360,
            WebkitFontSmoothing: "antialiased",
            fontVariantNumeric: "tabular-nums",
          },
          "button, input, select, textarea": { font: "inherit" },
          "input, textarea": { caretColor: accent },
          "::selection": { background: alpha(accent, 0.25), color: text },
          "*": {
            boxSizing: "border-box",
            scrollbarWidth: "thin",
            scrollbarColor: `${dark ? "#484e5c" : "#c2c8d2"} transparent`,
          },
          "::-webkit-scrollbar": { width: 7, height: 7 },
          "::-webkit-scrollbar-thumb": {
            backgroundColor: dark ? "#484e5c" : "#c2c8d2",
            borderRadius: 7,
            border: "2px solid transparent",
            backgroundClip: "padding-box",
          },
          ":focus-visible": {
            outline: `2px solid ${accent}`,
            outlineOffset: 3,
          },
          "@media (prefers-reduced-motion: reduce)": {
            "*, *::before, *::after": {
              animationDuration: "0.01ms !important",
              transitionDuration: "0.01ms !important",
            },
          },
        },
      },
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { backgroundImage: "none" } },
      },
      MuiButton: {
        defaultProps: { size: "small", disableElevation: true },
        styleOverrides: {
          root: {
            borderRadius: 9,
            minHeight: 32,
            padding: "5px 12px",
            whiteSpace: "nowrap",
          },
          outlined: {
            borderColor: divider,
            color: text,
            backgroundColor: paper,
            boxShadow: dark ? "none" : "0 1px 2px #20243406",
            "&:hover": {
              borderColor: accent,
              backgroundColor: alpha(accent, 0.06),
            },
          },
        },
      },
      MuiIconButton: {
        defaultProps: { size: "small" },
        styleOverrides: { root: { borderRadius: 8, padding: 7 } },
      },
      MuiTooltip: {
        defaultProps: { disableInteractive: true, enterDelay: 650 },
      },
      MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
      MuiFormControl: { defaultProps: { size: "small" } },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: 9, backgroundColor: paper, fontSize: 13 },
          notchedOutline: { borderColor: divider },
          input: { "&::placeholder": { color: secondary, opacity: 1 } },
        },
      },
      MuiChip: {
        defaultProps: { size: "small" },
        styleOverrides: {
          root: { height: 23, borderRadius: 6, fontSize: 10 },
          label: { paddingLeft: 7, paddingRight: 7 },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { padding: "7px 14px", borderColor: divider, fontSize: 12 },
          // Cover fractional scroll-container edges in WebKit while scrolling.
          stickyHeader: { top: -1 },
          head: {
            backgroundColor: dark ? "#242832" : "#f7f8fb",
            color: secondary,
            fontSize: 11,
            fontWeight: 600,
            lineHeight: 1.5,
            paddingTop: 9,
            paddingBottom: 9,
          },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: {
            "&.MuiTableRow-hover:hover": {
              backgroundColor: alpha(accent, dark ? 0.065 : 0.035),
            },
          },
        },
      },
      MuiDialog: {
        defaultProps: { fullWidth: true, maxWidth: "sm" },
        styleOverrides: {
          paper: {
            borderRadius: 18,
            boxShadow: dark ? "0 24px 80px #00000080" : "0 24px 80px #18243c33",
          },
        },
      },
      MuiBackdrop: {
        styleOverrides: {
          root: { backgroundColor: dark ? "#00000099" : "#14213d66" },
        },
      },
      MuiDialogTitle: {
        styleOverrides: {
          root: { padding: "22px 24px 18px", fontSize: 18, fontWeight: 650 },
        },
      },
      MuiDialogContent: { styleOverrides: { root: { padding: "20px 24px" } } },
      MuiDialogActions: {
        styleOverrides: { root: { padding: "16px 24px", gap: 6 } },
      },
      MuiAlert: { styleOverrides: { root: { fontSize: 12, borderRadius: 8 } } },
      MuiTabs: {
        styleOverrides: {
          root: { minHeight: 38 },
          indicator: { display: "none" },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: 33,
            minWidth: 0,
            padding: "7px 15px",
            marginRight: 6,
            borderRadius: 6,
            border: `1px solid ${divider}`,
            backgroundColor: dark ? "#252933" : "#f0f2f6",
            textTransform: "none",
            fontSize: 13,
            fontWeight: 500,
            "&.Mui-selected": {
              backgroundColor: dark ? "#246ed5" : "#eaf1ff",
              borderColor: dark ? "#246ed5" : "#dce8ff",
              color: dark ? "#ffffff" : accent,
              fontWeight: 650,
            },
          },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            height: 5,
            borderRadius: 4,
            backgroundColor: alpha(accent, 0.12),
          },
        },
      },
    },
  });
}
