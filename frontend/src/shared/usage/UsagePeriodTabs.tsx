import { Stack, Tab, Tabs, TextField, Tooltip } from "@mui/material";
import { localDate } from "../lib/date";

const periods = [
  { value: "today", label: "今天" },
  { value: "yesterday", label: "昨天" },
  { value: "7d", label: "七天" },
  { value: "month", label: "当月" },
  { value: "all", label: "累计" },
];

function dateLabel(value: Date) {
  return value.toLocaleDateString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
  });
}

export default function UsagePeriodTabs({
  period,
  setPeriod,
  date,
  setDate,
}: {
  period: string;
  setPeriod: (value: string) => void;
  date: string;
  setDate: (value: string) => void;
}) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - 6);
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const ranges: Record<string, string> = {
    today: dateLabel(today),
    yesterday: dateLabel(yesterday),
    "7d": `${dateLabel(weekStart)} — ${dateLabel(today)}（含今天）`,
    month: `${dateLabel(monthStart)} — ${dateLabel(today)}`,
    all: "当前 Provider 在本机保留的全部记录",
  };

  return (
    <Stack
      direction="row"
      sx={{
        gap: 1, mb: 1.25, flexShrink: 0,
        alignItems: "center", flexWrap: "wrap",
      }}
    >
      <Tabs
        aria-label="用量时间范围"
        value={periods.some((item) => item.value === period) ? period : false}
        onChange={(_, value: string) => setPeriod(value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{
          minHeight: 34,
          maxWidth: "100%",
          borderBottom: "1px solid",
          borderColor: "divider",
          "& .MuiTabs-indicator": { display: "block", height: 2, borderRadius: 0 },
          "& .MuiTabs-list": { gap: 1 },
        }}
      >
        {periods.map((item) => (
          <Tab
            key={item.value}
            value={item.value}
            label={item.label}
            title={ranges[item.value]}
            sx={{
              minHeight: 34,
              minWidth: 54,
              px: 1.75,
              py: 0.75,
              mr: 0,
              border: 0,
              borderRadius: 0,
              bgcolor: "transparent",
              fontSize: 12,
              color: "text.secondary",
              "&:hover": { bgcolor: "transparent" },
              "&.Mui-selected": {
                color: "primary.main", bgcolor: "transparent", fontWeight: 650,
              },
            }}
          />
        ))}
      </Tabs>
      {period === "date" && (
        <Tooltip title="沿用实时请求页选择的日期；点击时间 Tab 切换范围">
          <TextField
            type="date"
            value={date}
            onChange={(event) => {
              if (event.target.value) setDate(event.target.value);
            }}
            slotProps={{ htmlInput: { max: localDate(), "aria-label": "用量日期" } }}
            sx={{ width: 145 }}
          />
        </Tooltip>
      )}
    </Stack>
  );
}
