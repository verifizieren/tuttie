// The demo driver: lets the presentation clicker drive the REAL Tuttie wallet shown in the
// deck's iframe (same origin: /presentation/ next to /wallet/).
//
// It only supplies input and timing, the way a person holding the phone would: it taps the
// Tuttie card, sends the request to Tuttie as the wallet does (POST /chat), swipes the
// hotel cards with the wallet's own gestures (pointer events inside the iframe), and taps
// Approve in the wallet's approval sheet. Everything shown in the phone (offers, the refused
// forged business, bargaining, the approval, the signed booking) is the real wallet reacting to
// the real backend; nothing here draws UI or invents a result. If an element never appears,
// the step gives up quietly (a console warning) instead of faking it.
//
// Usage:
//   import { createDemo } from "./demo.js";
//   const demo = createDemo(document.querySelector("iframe.phone"));
//   for (const step of demo.steps) await step.run();   // or one per clicker press
//   await demo.reset();                                // fresh conversation, iframe reloaded

export const REQUEST =
  "A quiet room in Basel on 14 November. I arrive after midnight with my dog, under 160 francs.";
export const LIKED_HOTEL = /Gästehaus/i;       // Anna's Gästehaus am Rhein: liked, the others passed

const SWIPE_MS = 260;        // a quick, visible drag of a hotel card
const SWIPE_PX = 170;        // well past the wallet's decide distance (Deck.jsx DECIDE_PX 90)
const BETWEEN_CARDS_MS = 700;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/** @param iframe  the <iframe> showing /wallet/ (same origin as the deck) */
export function createDemo(iframe) {
  const doc = () => iframe.contentDocument;
  const win = () => iframe.contentWindow;
  const $ = selector => doc()?.querySelector(selector) || null;
  // Each reset starts a new generation; steps still waiting from an older one give up, so a
  // pending Approve or swipe never acts in the next run.
  let generation = 0;

  /** Poll until `find()` returns something truthy; null after `timeout` ms or after a reset
   *  (never throws). */
  async function waitFor(find, timeout = 10000, every = 100) {
    const mine = generation;
    const end = performance.now() + timeout;
    for (;;) {
      if (mine !== generation) return null;
      try {
        const found = find();
        if (found) return found;
      } catch { /* the iframe may be reloading */ }
      if (performance.now() > end) return null;
      await sleep(every);
    }
  }

  /** A pointer event of the iframe's own window, so the wallet's handlers read it like a finger. */
  function pointer(target, type, x, y) {
    const PointerEvent = win().PointerEvent;
    target.dispatchEvent(new PointerEvent(type, {
      bubbles: true, cancelable: true, composed: true, pointerId: 7, pointerType: "touch",
      isPrimary: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1,
    }));
  }

  const centre = el => {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  };

  /** The wallet's microphone off, before the card opens: the deck's iframe may not use the
   *  microphone, and a refused one shows "Microphone blocked" under Tuttie's eyes. Muted from
   *  the start, the wallet never asks for it (hooks/useVoice.js), so no note shows. The dock's
   *  own mute button (a click works while the closed dock is hidden). */
  function muteMicrophone() {
    $('.dock button[aria-label="Mute microphone"]')?.click();
  }

  /** A finger tap on the closed Tuttie card (useCardGestures reads a down/up without movement). */
  async function openTuttie() {
    if ($(".app.open")) return true;
    const card = await waitFor(() => $(".card.agent"));
    if (!card) return false;
    muteMicrophone();
    const target = card.querySelector("canvas") || card;
    const { x, y } = centre(card);
    pointer(target, "pointerdown", x, y);
    await sleep(90);
    pointer(target, "pointerup", x, y);
    return Boolean(await waitFor(() => $(".app.open"), 3000));
  }

  /** Send the request the way the wallet itself does (POST /chat, its conversation id from
   *  GET /history, the session cookie shared with the wallet), without the text field: in the
   *  wallet's typing mode Tuttie's eyes close, and here they should stay awake and show her
   *  thinking. The server opens the turn with a "turn" event, which the wallet shows like one
   *  it sent itself (as it does for a spoken request). */
  async function ask() {
    if (!(await openTuttie())) return warn("ask: the Tuttie card did not open");
    const history = await fetch("/history", { cache: "no-store" });
    const conversationId = history.headers.get("X-Conversation-ID");
    if (!history.ok || !conversationId) return warn("ask: no conversation to send to");
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: REQUEST, conversation_id: conversationId }),
    });
    // Refused (409 another chat, 429 too many requests): say so in the console, never throw.
    if (!response.ok) warn(`ask: the request was not taken (HTTP ${response.status})`);
  }

  /** Drag the top hotel card sideways with a few pointer moves and let go (Deck.jsx handlers). */
  async function swipe(card, verdict) {
    const { x, y } = centre(card);
    const dir = verdict === "like" ? 1 : -1;
    const moves = 8;
    pointer(card, "pointerdown", x, y);
    for (let i = 1; i <= moves; i++) {
      await sleep(SWIPE_MS / moves);
      pointer(card, "pointermove", x + dir * SWIPE_PX * (i / moves), y + i);
    }
    pointer(card, "pointerup", x + dir * SWIPE_PX, y + moves);
  }

  /** Like Gästehaus am Rhein, pass every other hotel, until the deck is done. If Gästehaus did
   *  not offer this time, the last card is liked so the booking can still go on. */
  async function like() {
    const first = await waitFor(() => $(".deck .swipe-card:last-child"), 90000, 250);
    if (!first) return warn("like: no hotel cards arrived");
    let liked = false;
    for (let guard = 0; guard < 12; guard++) {
      // The top card is the last one in the stack (Deck.jsx renders the next card first).
      const top = await waitFor(() => $(".deck .swipe-card:last-child"), 2500);
      if (!top) break;  // the deck is done: the wallet sends the booking request itself
      const name = top.querySelector(".swipe-name")?.textContent || "";
      const isLast = /^(\d+) of \1$/.test($(".deck-count")?.textContent || "");
      const verdict = LIKED_HOTEL.test(name) || (isLast && !liked) ? "like" : "pass";
      if (verdict === "like") liked = true;
      if (isLast && verdict === "like" && !LIKED_HOTEL.test(name)) warn(`like: ${LIKED_HOTEL} did not offer; liking ${name}`);
      await swipe(top, verdict);
      // Wait for the card to leave (its node is replaced by the next one, or the deck goes).
      await waitFor(() => $(".deck .swipe-card:last-child") !== top, 3000, 50);
      if (isLast) break;
      await sleep(BETWEEN_CARDS_MS);
    }
  }

  /** Tap Approve in the wallet's approval sheet (it runs its own Face ID-style scan). */
  async function approve() {
    const button = await waitFor(() => $(".sheet .sheet-buttons button.approve"), 60000, 200);
    if (!button) return warn("approve: no approval sheet appeared");
    button.click();
  }

  function warn(message) {
    console.warn(`[demo] ${message}`);
  }

  /** Never let a step throw into the deck's clicker handler. */
  const safe = run => async () => {
    try { await run(); } catch (e) { warn(`step failed: ${e?.message || e}`); }
  };

  const steps = [
    // Run by the deck on entering the demo beat, while the eyes move into the phone.
    { id: "open", label: "Open Tuttie", run: safe(async () => { if (!(await openTuttie())) warn("open: card did not open"); }) },
    { id: "ask", label: "Send the request", run: safe(ask) },
    { id: "forged", label: "Forged seal: never asked", run: async () => {} },  // a cue for the side word only
    { id: "like", label: "Swipe: like Gästehaus am Rhein", run: safe(like) },
    { id: "approve", label: "Approve", run: safe(approve) },
    { id: "done", label: "Booking", run: safe(async () => {
      if (!(await waitFor(() => $(".booking"), 60000, 250))) warn("done: no booking card yet");
    }) },
  ];

  /** Start over: a fresh conversation on the server, then the wallet reloads from it. */
  async function reset() {
    generation++;
    try {
      await fetch("/reset", { method: "POST" });
    } catch (e) {
      warn(`reset: ${e?.message || e}`);
    }
    await new Promise(resolve => {
      iframe.addEventListener("load", resolve, { once: true });
      try { win().location.reload(); } catch { iframe.src = iframe.src; }
      setTimeout(resolve, 8000);
    });
  }

  return { steps, reset, fallback: "media/fallback.webm" };
}
