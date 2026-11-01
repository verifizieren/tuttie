// Presenter view: the current and next spoken line, a clock, and time against the plan.
// Opened by N in the deck; kept in sync over a BroadcastChannel. Keys pressed here drive the deck.

import { BEATS, flatten, clock } from "./beats.js";

const $ = id => document.getElementById(id);
const channel = new BroadcastChannel("tuttie-deck");
let state = null;

function beatsOf(ids) {
  return ids.map(id => BEATS.find(beat => beat.id === id)).filter(Boolean);
}

function render() {
  if (!state) return;
  const beats = beatsOf(state.beats);
  const flat = flatten(beats);
  const here = flat[state.pos], next = flat[state.pos + 1];
  if (!here) return;
  const n = here.beat.steps.length;
  $("where").innerHTML = `${here.beatIndex} · ${here.beat.title}<span>${n > 1 ? `step ${here.index + 1} of ${n}` : ""}</span>`;
  const waiting = (state.pending || []).length ? `WAITING: ${state.pending.join(", ")}` : "";
  $("flags").textContent = [state.black && "BLACK", state.fallback && "RECORDING", waiting].filter(Boolean).join("   ");
  $("cue").textContent = here.step.cue;
  $("now").textContent = here.step.spoken || "(silence)";
  $("nextcue").textContent = next ? next.step.cue : "End.";
  $("next").textContent = next ? next.step.spoken || "(silence)" : "";
  $("plan").innerHTML = beats.filter(b => b.from !== null).map(b => {
    const cls = b.id === here.beat.id ? "current" : b.id in state.entered ? "done" : "";
    const actual = b.id in state.entered ? clock(state.entered[b.id]) : "–";
    return `<div class="${cls}"><strong>${b.title}</strong>${clock(b.from)}–${clock(b.to)} · ${actual}</div>`;
  }).join("");
  tick();
}

function tick() {
  const now = new Date();
  $("clock").textContent = now.toTimeString().slice(0, 5);
  if (!state?.startedAt) {
    for (const id of ["beat", "delta", "elapsed"]) $(id).textContent = "0:00";
    $("delta").className = "";
    return;
  }
  const elapsed = (Date.now() - state.startedAt) / 1000;
  const beat = flatten(beatsOf(state.beats))[state.pos]?.beat;
  $("elapsed").textContent = clock(elapsed);
  if (beat && beat.from !== null && beat.id in state.entered) {
    const inBeat = elapsed - state.entered[beat.id];
    $("beat").textContent = `${clock(inBeat)} / ${clock(beat.to - beat.from)}`;
    // Late if this beat started later than planned, or is running past its planned end.
    const delta = Math.max(state.entered[beat.id] - beat.from, elapsed - beat.to);
    $("delta").textContent = `${delta >= 0 ? "+" : ""}${clock(delta)}`;
    $("delta").className = delta > 2 ? "late" : delta < -2 ? "early" : "";
  }
}

channel.addEventListener("message", ({ data }) => {
  if (data?.type === "state") { state = data; render(); }
});
channel.postMessage({ type: "hello" });
setInterval(tick, 250);

addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.key === "n" || e.key === "N" || e.key === "f" || e.key === "F") return;
  channel.postMessage({ type: "key", key: e.key });
  if ([" ", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"].includes(e.key)) e.preventDefault();
});
