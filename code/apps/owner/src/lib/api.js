// Talks to the business's node (code/node/owner.py: /owner/overview and /owner/deploy).
// The owner view shows one business. Which node: `?node=<url>` in the page address, else
// VITE_NODE_URL, else the Gästehaus am Rhein's node (port 4009) on the host serving this page.

const DEFAULT_NODE_PORT = 4009;
const TOKEN_KEY = "tuttie_owner_token";

export function nodeUrl() {
  const fromAddress = new URLSearchParams(location.search).get("node");
  const url = fromAddress || import.meta.env.VITE_NODE_URL
    || `${location.protocol}//${location.hostname}:${DEFAULT_NODE_PORT}`;
  return url.replace(/\/$/, "");
}

// The token lives in this tab only (sessionStorage), never in the address or on disk.
export const savedToken = () => sessionStorage.getItem(TOKEN_KEY) || "";
export const saveToken = token => sessionStorage.setItem(TOKEN_KEY, token);
export const forgetToken = () => sessionStorage.removeItem(TOKEN_KEY);

/** An error with the HTTP status (0 when the node cannot be reached), so the page can react.
 *  `errors` holds the node's list of {path, message} when it refused settings (422). */
export class OwnerApiError extends Error {
  constructor(message, status, errors = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

async function request(path, token, { signal, body } = {}) {
  let response;
  try {
    response = await fetch(`${nodeUrl()}/owner${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new OwnerApiError("The business node cannot be reached.", 0);
  }
  if (!response.ok) {
    const detail = await response.json().then(reply => reply.detail, () => null);
    if (detail && typeof detail === "object" && detail.errors) {
      throw new OwnerApiError(detail.errors[0]?.message || "The settings were refused.", response.status, detail.errors);
    }
    throw new OwnerApiError(typeof detail === "string" ? detail : `HTTP ${response.status}`, response.status);
  }
  return response.json();
}

/** The business as it is live right now. */
export const fetchOverview = (token, signal) => request("/overview", token, { signal });

/** Deploy `settings` on top of `baseVersion`; answers with the new live overview. */
export const deploySettings = (token, baseVersion, settings) =>
  request("/deploy", token, { body: { base_version: baseVersion, settings } });
