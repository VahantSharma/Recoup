// The one deliberately live call this screen makes -- everything else reads a
// committed artifact (src/lib/artifacts/). Talks to app.main's FastAPI endpoint
// (`cd backend && uvicorn app.main:app --reload`), not the static export pipeline, so
// it is never routed through the artifact loader's import-boundary check.
const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

// Vite exposes only VITE_-prefixed env vars to client code; falls back to the
// documented default `uvicorn app.main:app --reload` port when unset.
const BASE_URL = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_LIVE_API_BASE_URL
  ?? DEFAULT_BASE_URL;

export interface LiveActionResponse {
  case_id: string;
  razorpay_payment_id: string;
  attempt_number: number;
  reconciled_status_real: string;
  reconciled_status_used: string;
  reconcile_overridden: boolean;
  gate_decision: "approved" | "rejected";
  gate_reason: string;
  action_taken: "created" | "replayed_no_op" | "refused";
  idempotency_key: string | null;
  payment_link_short_url: string | null;
}

export class LiveApiUnreachableError extends Error {}

export async function verifyRecoveryAction(
  attemptNumber: number,
  simulateResolvedElsewhere: boolean,
): Promise<LiveActionResponse> {
  const url = `${BASE_URL}/api/live/verify-recovery-action?attempt_number=${attemptNumber}&simulate_resolved_elsewhere=${simulateResolvedElsewhere}`;
  let res: Response;
  try {
    res = await fetch(url, { method: "POST" });
  } catch {
    // A fetch that never reaches the network (backend not running, CORS misconfigured)
    // throws a generic TypeError with no useful message -- translate it into the one
    // thing a reviewer actually needs to know.
    throw new LiveApiUnreachableError(
      `Could not reach ${BASE_URL}. Is the backend running? cd backend && uvicorn app.main:app --reload`,
    );
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Live endpoint returned HTTP ${res.status}${body ? `: ${body}` : ""}`);
  }
  return (await res.json()) as LiveActionResponse;
}
