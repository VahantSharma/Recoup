import "./Badge.css";
import type { Tone } from "../lib/outcome";

/** Colored text on a 12%-opacity tint of the same hue -- never a solid fill. The one
 * reusable primitive for every outcome/status label on the screen. */
export function Badge({ label, tone }: { label: string; tone: Tone }) {
  return <span className={`badge badge-${tone}`}>{label}</span>;
}
