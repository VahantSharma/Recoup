/** Shared formatting helpers for the Stage 3 screens -- paise is this project's one
 * money unit everywhere (see docs/assumptions.md's unit conventions); every screen
 * formats it the same way rather than each re-deriving its own rounding. */

export function formatPaise(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function formatPercent(fraction: number, digits = 1): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function formatSigned(fraction: number, digits = 2): string {
  const pct = fraction * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}
