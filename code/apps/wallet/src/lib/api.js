// Calls to the assistant service (code/assistant/app.py). The wallet is served by the same
// service, so every path is relative to the site; in development Vite forwards them.

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} failed: HTTP ${response.status}`);
  return response.json();
}

/** Ask Tuttie something; the answer arrives later as an "answer" event on the stream. */
export const sendChat = message => post("/chat", { message });

/** The user's decision on a pending approval; the assistant signs it with the user's key. */
export const decide = (approvalId, decision) => post(`/approvals/${approvalId}`, { decision });

/** Start over: a new conversation and an empty timeline. */
export const resetConversation = () => post("/reset");
