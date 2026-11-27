import { Box, Stack, Tooltip, Typography } from "@mui/material";
import ArrowDownwardRounded from "@mui/icons-material/ArrowDownwardRounded";
import ArrowUpwardRounded from "@mui/icons-material/ArrowUpwardRounded";
import CachedRounded from "@mui/icons-material/CachedRounded";
import PsychologyOutlined from "@mui/icons-material/PsychologyOutlined";
import { tokens } from "../lib/format";
import { mono } from "../theme";

interface Props {
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
}

export function TokenConsumption(row: Props) {
  const label = `输入 ${row.input_tokens.toLocaleString()} Token，缓存读取 ${row.cached_input_tokens.toLocaleString()} Token，缓存写入 ${row.cache_write_input_tokens.toLocaleString()} Token；输出 ${row.output_tokens.toLocaleString()} Token，其中思考 ${row.reasoning_output_tokens.toLocaleString()} Token，思考已包含在输出中`;
  const icon = { fontSize: 13, flexShrink: 0 };
  return (
    <Tooltip title={
      <Box sx={{ whiteSpace: "nowrap" }}>
        <Box>输入：{row.input_tokens.toLocaleString()} Token</Box>
        <Box>输出：{row.output_tokens.toLocaleString()} Token</Box>
        <Box>思考：{row.reasoning_output_tokens.toLocaleString()} Token（已包含在输出中）</Box>
        <Box>缓存：读取 {row.cached_input_tokens.toLocaleString()} Token，写入 {row.cache_write_input_tokens.toLocaleString()} Token</Box>
      </Box>
    }>
      <Box aria-label={label} sx={{ display: "inline-block", whiteSpace: "nowrap" }}>
        <Stack direction="row" spacing={0.6} sx={{ alignItems: "center", justifyContent: "flex-end" }}>
          <ArrowDownwardRounded aria-hidden sx={{ ...icon, color: "text.secondary" }} />
          <Typography component="span" sx={{ fontFamily: mono, fontSize: 12, fontWeight: 600 }}>{tokens(row.input_tokens)}</Typography>
          <CachedRounded aria-hidden sx={{ ...icon, color: "text.secondary" }} />
          <Typography component="span" variant="caption" color="textSecondary" sx={{ fontFamily: mono }}>{tokens(row.cached_input_tokens)}</Typography>
        </Stack>
        <Stack direction="row" spacing={0.6} sx={{ alignItems: "center", justifyContent: "flex-end" }}>
          <ArrowUpwardRounded aria-hidden sx={{ ...icon, color: "text.secondary" }} />
          <Typography component="span" sx={{ fontFamily: mono, fontSize: 12, fontWeight: 600 }}>{tokens(row.output_tokens)}</Typography>
          <PsychologyOutlined aria-hidden sx={{ ...icon, color: "text.secondary" }} />
          <Typography component="span" variant="caption" color="textSecondary" sx={{ fontFamily: mono }}>{tokens(row.reasoning_output_tokens)}</Typography>
        </Stack>
      </Box>
    </Tooltip>
  );
}
