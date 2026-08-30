/**
 * The one place every screen is named, hashed, and described. Nav, the landing
 * page's cards, and the guided tour all read from this array — a screen exists here
 * exactly once, or a reviewer can end up looking at three different labels for the
 * same thing across three different surfaces. Order here IS tour order.
 *
 * `question` is the thing a payments engineer actually wants answered, in their own
 * words — never the internal screen name. `purpose` is the same idea, phrased as the
 * one-line statement shown at the top of the screen itself, so nobody is ever
 * mid-screen wondering what they're looking at.
 */
export interface ScreenMeta {
  id: string;
  hash: string; // window.location.hash value, including the leading '#'
  navLabel: string;
  question: string; // landing card + tour step label
  purpose: string; // one-line purpose statement shown atop the screen
  summary: string; // one sentence for the landing card body
}

export const SCREENS: ScreenMeta[] = [
  {
    id: "case-audit",
    hash: "#case-audit",
    navLabel: "Case Audit",
    question: "What does one case actually look like?",
    purpose: "This screen follows one failed payment through every real decision made about it, start to finish.",
    summary:
      "One failed payment, five steps: why it failed, how we classified it, what each safety check decided (in order), what happened next, and how it ended.",
  },
  {
    id: "ablation",
    hash: "#ablation",
    navLabel: "Ablation Table",
    question: "Does it actually recover more money — safely?",
    purpose: "This screen compares every approach against a group of identical payments where we did nothing, so any improvement you see is real, not payments that would have come back anyway.",
    summary:
      "Every approach tested on the exact same payments. How much money it recovered sits right next to how many safety rules it broke — never hidden in a separate table.",
  },
  {
    id: "sliders",
    hash: "#sliders",
    navLabel: "Assumption Sliders",
    question: "What if our assumptions are wrong?",
    purpose: "This screen tests what happens if our best guesses turn out to be wrong — does the result still hold up across the whole range of what could actually be true?",
    summary:
      "Every number we had to guess at gets tested across a wide range, not just one guess — see whether the result still holds up no matter which guess turns out right.",
  },
  {
    id: "decomposition",
    hash: "#decomposition",
    navLabel: "Three-Bound Decomposition",
    question: "How much better could this possibly get?",
    purpose: "This screen measures the ceiling — the most a system with perfect, impossible-to-have information could ever add on top of what we already do.",
    summary:
      "What we actually achieve, the best we could do using only real information, and the absolute best with a perfect crystal ball — three different claims, never mashed into one number.",
  },
  {
    id: "model",
    hash: "#model",
    navLabel: "Model Layer",
    question: "Where's the AI — and why isn't it doing more?",
    purpose: "This screen answers \"where's the AI, then?\" — a rule we wrote down in advance, applied automatically, that both AI providers we tried ended up tripping.",
    summary:
      "No AI model is actually used to make the real decisions. We wrote a rule down first, then made real calls to two AI providers — both tripped the rule, and our commit history proves the rule was written before either was called.",
  },
];

export const LANDING_HASH = "#";

export function screenByHash(hash: string): ScreenMeta | undefined {
  return SCREENS.find((s) => s.hash === hash);
}

export function screenIndex(id: string): number {
  return SCREENS.findIndex((s) => s.id === id);
}
