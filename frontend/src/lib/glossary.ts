/**
 * One definitions file for every term a reviewer might not already share our meaning
 * for. `<GlossaryTerm term="corpus">corpus</GlossaryTerm>` wraps the word itself
 * wherever it's used, so a reviewer never has to go hunting for a separate "what does
 * this mean" icon to understand a sentence that's already in front of them.
 */
export const GLOSSARY: Record<string, string> = {
  corpus: "The batch of payment cases a test run works through — some are real, most are built from Razorpay's own published failure reasons so we have enough cases to measure anything meaningful.",
  arm: "One approach being tested — \"do nothing,\" \"retry everything,\" \"our rules engine,\" and so on. Every arm runs on the exact same batch of payments, so comparing them is fair.",
  lift: "How much better one approach did than another, on the identical batch of payments. Never a raw number on its own — always the difference between two arms.",
  control: "The arm that does nothing at all. It exists so we can tell how many payments would have come back anyway, with no help from us — without it, we couldn't tell real recovery from money that was never actually at risk.",
  seed: "A starting number that makes a randomized test batch reproducible — the same seed always builds the exact same batch of payments, so a result can be checked again and again, not just trusted once.",
  manifest: "The receipt attached to every number on this site: which code produced it, which exact data it ran on, and when. Click any number to see its manifest.",
  "idempotency key": "A fingerprint for one specific retry attempt. If that exact attempt is ever accidentally repeated — say, after a crash — this fingerprint catches it and the repeat does nothing, instead of charging the customer a second time.",
  "common random numbers": "A statistics technique: giving every arm the same underlying \"luck\" on the same payment, so a difference between two arms reflects a real difference in what they decided — not one arm just getting luckier random draws than the other.",
  "soft decline": "A failure that's genuinely worth retrying — like not enough money in the account right now. Different from a \"hard\" decline (a closed or stolen card, never retried) or a \"technical\" one (a timeout, safe to retry fast).",
  "oracle bound": "The absolute best score possible if a system had perfect, impossible-to-have information — like already knowing which payments will succeed before trying them. No real system can ever reach it; it exists only to show the honest ceiling.",
};

export type GlossaryKey = keyof typeof GLOSSARY;
