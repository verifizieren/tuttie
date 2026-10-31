// Calls to the assistant service (code/assistant/app.py). The wallet is served by the same
// service, so every path is relative to the site; in development Vite forwards them.

export const UNREACHABLE = "Tuttie is unreachable right now";

/** The line the user sees for a failed call: the server's own reason when it wrote one
 *  (FastAPI's `detail` string), else a plain sentence; never a raw status, "[object Object]"
 *  (a 422's list of field errors) or a browser message such as "Failed to fetch". */
export function errorText(status, body) {
  if (typeof body?.detail === "string" && body.detail.trim()) return body.detail;
  if (status === 422) return "Tuttie could not read that request. Please try again.";
  if (status === 409) return "Tuttie is busy with something else right now";
  if (status && status < 500) return "Tuttie could not do that right now";
  return status ? "Tuttie ran into a problem. Please try again in a moment." : UNREACHABLE;
}

async function post(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(UNREACHABLE);  // offline or the server is down: no status
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    // The status travels with the error, so callers can tell an expired chat (404/410) from a busy one (409).
    throw Object.assign(new Error(errorText(response.status, error)), { status: response.status });
  }
  // A page instead of JSON (a proxy's error page) is a failure like any other.
  return response.json().catch(() => { throw Object.assign(new Error(errorText(502)), { status: 502 }); });
}

/** Ask Tuttie something as a new turn; returns { turn_id }. The answer arrives later as an
 *  "answer" event with that turn id. `firstTool` fixes Tuttie's first step (after swiping the
 *  cards: "book"); `said` is what the user sees as their message, if not the message itself. */
export const sendChat = (message, firstTool = null, conversationId = null, said = null) =>
  post("/chat", { message, first_tool: firstTool, conversation_id: conversationId, said });

/** The user's decision on a pending approval; the assistant signs it with the user's key.
 *  `allowMandate` also signs the mandate the approval offered (e.g. for the city tax). */
export const decide = (approvalId, decision, allowMandate = false) =>
  post(`/approvals/${approvalId}`, { decision, allow_mandate: allowMandate });

/** Start over: a new conversation and an empty timeline. */
export const resetConversation = () => post("/reset");

export const newConversation = () => post("/conversations");
export const resumeConversation = id => post(`/conversations/${encodeURIComponent(id)}/resume`);
