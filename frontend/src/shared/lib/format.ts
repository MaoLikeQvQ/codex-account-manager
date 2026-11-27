export const tokens = (n?: number) =>
  n == null
    ? "—"
    : Math.abs(n) >= 1e6
      ? `${(n / 1e6).toFixed(2)}M`
      : Math.abs(n) >= 1e3
        ? `${(n / 1e3).toFixed(1)}K`
        : n.toLocaleString("en-US");
export const money = (n?: number, digits = 3) =>
  n == null
    ? "—"
    : `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
