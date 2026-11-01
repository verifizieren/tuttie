// The pitch, beat by beat: planned time, and per step what the speaker says and what the click
// does. Shared by the deck (index.html) and the presenter view (presenter.html), and the source
// of SPEAKER-NOTES.md. The screen never shows the spoken line; this file is only for the speaker.
//
// A beat is one screen. Each click moves one step; a beat's first step is shown on entering it.
// Steps in beat "demo" carry the id of the matching step in demo.js (createDemo().steps).

/** Beat 7 (Anna's owner view) is optional: set to false, or open the deck with ?owner=0. */
export const OWNER_BEAT = true;

export const BEATS = [
  {
    id: "dark", title: "Walk on", from: null, to: 0,
    steps: [
      { cue: "Empty. Walk on, hold the phone, two seconds of silence.", spoken: "" },
    ],
  },
  {
    id: "anna", title: "Anna", from: 0, to: 14,
    steps: [
      { cue: "Click: Anna's guesthouse fades in. The timer starts here.",
        spoken: "This is Anna's guesthouse in Basel. Seven rooms, quiet, dogs welcome. No marketing team." },
    ],
  },
  {
    id: "scam", title: "The scam", from: 14, to: 30,
    steps: [
      { cue: "Empty.",
        spoken: "Tonight more people won't search for her. Their AI will. And the AI sees what we all see:" },
      { cue: "Click: the cheap listing appears.",
        spoken: "page nine, behind a scam. Super quiet, CHF 99, pay by bank transfer." },
    ],
  },
  {
    id: "tuttie", title: "Tuttie", from: 30, to: 40,
    steps: [
      { cue: "Click: Tuttie's eyes fade in.",
        spoken: "So we turned the web around. This is Tuttie. She lives in my wallet, and she works only for me." },
    ],
  },
  {
    id: "demo", title: "Demo", from: 40, to: 115,
    steps: [
      { cue: "Click: the eyes move into the phone, the wallet opens and Tuttie is awake.", spoken: "" },
      { demo: "ask", cue: "Click as you start the sentence: the request is sent.",
        spoken: "Tuttie, a quiet room in Basel on the fourteenth, I arrive after midnight with my dog, under one-sixty. [pause] She doesn't search. She posts my request, and only businesses with a valid seal are woken. Watch the cheap one." },
      { demo: "forged", cue: "Click on \"Forged seal\": side word Never asked. (red)",
        spoken: "[pause] Forged seal. Never asked." },
      { demo: "like", cue: "Click: swipe the cards, like Gästehaus am Rhein, pass the others.",
        spoken: "[pause] Anna's agent offered 135. Tuttie already bargained: 128. I still choose." },
      { demo: "approve", cue: "Click on \"One tap\": Approve is tapped, side word One tap. (blue)",
        spoken: "And nothing happens without me. One tap, signed with my key, for exactly that price." },
      { demo: "done", cue: "Click: hold on the booking card. Two seconds of silence.", spoken: "" },
    ],
  },
  {
    id: "honest", title: "What is demo", from: 115, to: 125,
    steps: [
      { cue: "Click: empty.",
        spoken: "The hotels and the register are demo. The signatures are real." },
    ],
  },
  {
    id: "signature", title: "Website to signature", from: 125, to: 145,
    steps: [
      { cue: "Click: 2000, website.", spoken: "In 2000 a business needed a website." },
      { cue: "Click: 2033, signature.",
        spoken: "In five to ten years, it needs a signature: a signed agent that answers for it. Anna sets her prices and limits once. Her agent does the rest." },
    ],
  },
  {
    id: "owner", title: "One more thing", from: 145, to: 160, optional: true,
    steps: [
      { cue: "Click: One more thing.", spoken: "One more thing." },
      { cue: "Click: Anna's owner view.",
        spoken: "This is Anna's side. She approves what her agent may say, in plain words." },
    ],
  },
  {
    id: "close", title: "Close", from: 160, to: 180,
    steps: [
      { cue: "Click: first line.", spoken: "Signed businesses reach you." },
      { cue: "Click: second line.", spoken: "Fakes never do." },
      { cue: "Click: QR code. Stay until the end.", spoken: "Tuttie is live. Wake yours." },
    ],
  },
];

/** The beats in play: drops the optional owner beat when it is switched off. */
export function activeBeats(search = "") {
  const ownerOff = !OWNER_BEAT || new URLSearchParams(search).get("owner") === "0";
  return BEATS.filter(beat => !(beat.optional && ownerOff));
}

/** All steps in order, each as { beat, step, beatIndex }. */
export function flatten(beats) {
  return beats.flatMap((beat, beatIndex) => beat.steps.map((step, index) => ({ beat, beatIndex, step, index })));
}

/** m:ss for a number of seconds (negative gets a minus sign). */
export function clock(seconds) {
  const sign = seconds < 0 ? "-" : "";
  const s = Math.floor(Math.abs(seconds));
  return `${sign}${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
