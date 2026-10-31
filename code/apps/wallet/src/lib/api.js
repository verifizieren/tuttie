// Calls to the assistant service (code/assistant/app.py). The wallet is served by the same
// service, so every path is relative to the site; in development Vite forwards them.

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    // The status travels with the error, so callers can tell an expired chat (404/410) from a busy one (409).
    throw Object.assign(new Error(error.detail || `${path} failed: HTTP ${response.status}`), { status: response.status });
  }
  return response.json();
}

/** Ask Tuttie something; the answer arrives later as an "answer" event on the stream.
 *  `firstTool` fixes Tuttie's first step (after swiping the cards: "negotiate"). */
export const sendChat = (message, firstTool = null, conversationId = null) =>
  post("/chat", { message, first_tool: firstTool, conversation_id: conversationId });

/** The user's decision on a pending approval; the assistant signs it with the user's key.
 *  `allowMandate` also signs the mandate the approval offered (e.g. for the city tax). */
export const decide = (approvalId, decision, allowMandate = false) =>
  post(`/approvals/${approvalId}`, { decision, allow_mandate: allowMandate });

/** Start over: a new conversation and an empty timeline. */
export const resetConversation = () => post("/reset");

export const newConversation = () => post("/conversations");
export const resumeConversation = id => post(`/conversations/${encodeURIComponent(id)}/resume`);
