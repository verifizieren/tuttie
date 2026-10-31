// Tuttie's voice in the wallet. The first tap on Tuttie joins this conversation's LiveKit room
// (token from POST /voice/token); after that the wallet stays in the room with the microphone
// off while the card is closed, so the voice agent is already there: opening the card again
// only switches the microphone on and Tuttie's voice up. It sends the microphone, plays
// Tuttie's voice, and passes both voice levels to Tuttie's presence (onLevels), which moves the
// eyes (lib/faceDirector.js): they pulse while Tuttie speaks and open up while the user talks.
// Speech becomes a message to the same Tuttie as typing (code/voice/agent.py); without voice
// configured on the server the wallet simply stays text-only. What Tuttie says also arrives as
// text, word by word in step with its voice (LiveKit's "lk.transcription" streams), so the wallet
// can show an answer as it is spoken.
// When the wallet is hidden (another app, locked phone) the room is left; it rejoins on return.
import { useEffect, useRef, useState } from "react";
import { report, watchIce } from "../lib/iceReport.js";

const LEVEL_MS = 50;       // how often the voice levels go to the presence (and so to the eyes)
const RETRY_MS = 2000;     // rejoin after a dropped connection
// The phone's own clean-up of the microphone: background noise and Tuttie's own voice are
// filtered before anything is sent; voice isolation (e.g. on iPhones) is the stronger form.
const MIC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, voiceIsolation: true };

function visible() {
  return document.visibilityState === "visible";
}

/**
 * @param active  voice mode is on (the card is open and the user is not typing)
 * @param onSpeech  ({ id, text, done }) => void: Tuttie's words so far, as it speaks them
 * @param onLevels  (speaking, hearing) => void: both voice levels (0..1), every LEVEL_MS while live,
 *                  and (0, 0) when voice stops; feeds Tuttie's presence (hooks/usePresence.js)
 * @param conversationId  the conversation on screen (null while loading): the room belongs to it
 * @returns { state, unlockAudio, muted, toggleMute }: state is "off" | "connecting" | "ready"
 *          (joined, waiting in the background) | "live" (voice mode on) | "unavailable"; call
 *          unlockAudio() from a tap if the browser blocked Tuttie's voice; muted keeps the
 *          microphone off (e.g. in a noisy room) until toggled again
 */
export default function useVoice(active, onSpeech, onLevels, conversationId) {
  const speech = useRef(onSpeech);
  speech.current = onSpeech;
  const levelsTo = useRef(onLevels);
  levelsTo.current = onLevels;
  const activeRef = useRef(active);
  activeRef.current = active;
  const [joined, setJoined] = useState(null);  // the connected Room, or null
  const [state, setState] = useState("off");
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const [attempt, setAttempt] = useState(0);
  const [shown, setShown] = useState(visible());

  useEffect(() => {
    const onVisibility = () => setShown(visible());
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  // The first tap joins the room (an iPhone sets up the connection only while the microphone
  // is in use, so it must be captured first); after that the room stays joined while the card
  // is closed, microphone off, so opening it again is instant. If the room is left while the
  // card is closed (new chat, wallet hidden), it is joined again on the next tap.
  const [wanted, setWanted] = useState(false);
  useEffect(() => { if (active) setWanted(true); }, [active]);

  useEffect(() => {
    // Only once the conversation is loaded: its request also sets this browser's session cookie,
    // and a token fetched before that would tie the room to another session (voice would go
    // into a conversation the screen does not show).
    if (!shown || !conversationId || !wanted) return undefined;
    let closed = false, lk = null, retry = null;
    setState("connecting");
    (async () => {
      const response = await fetch("/voice/token", { method: "POST" });
      if (!response.ok) throw new Error("voice is not configured");
      const [{ url, token }, { Room, RoomEvent, Track, createLocalAudioTrack }] =
        await Promise.all([response.json(), import("livekit-client")]);
      if (closed) return;
      // The microphone first, then the connection (see above). Muted: connect without it.
      const mic = activeRef.current && !mutedRef.current ? await createLocalAudioTrack(MIC).catch(() => null) : null;
      if (closed) { mic?.stop(); return; }
      watchIce();  // a failed connection on a phone is reported to the server's log
      // The classic two connections (publish, subscribe), not the newer single one: phones'
      // Safari joined but never connected with it.
      // The microphone is released while the card is closed (stopMicTrackOnMute).
      lk = new Room({ adaptiveStream: true, dynacast: true, singlePeerConnection: false, stopMicTrackOnMute: true });
      lk.on(RoomEvent.TrackSubscribed, track => {
        if (track.kind !== Track.Kind.Audio) return;
        const audio = track.attach();  // Tuttie's voice, silent until voice mode is on
        audio.hidden = true;
        audio.muted = !activeRef.current;
        audio.dataset.tuttie = "";
        document.body.appendChild(audio);
      });
      lk.on(RoomEvent.TrackUnsubscribed, track => track.detach().forEach(el => el.remove()));
      lk.on(RoomEvent.Disconnected, reason => {
        report({ state: "room disconnected", reason });
        if (closed) return;
        setJoined(null);
        if (!activeRef.current) return setWanted(false);  // joined again on the next tap
        retry = setTimeout(() => setAttempt(n => n + 1), RETRY_MS);
      });
      // Tuttie's words, in step with its voice. The user's own words come on the same topic,
      // marked with the user's microphone track: those are skipped.
      lk.registerTextStreamHandler("lk.transcription", async reader => {
        const track = reader.info.attributes?.["lk.transcribed_track_id"];
        const mine = [...lk.localParticipant.trackPublications.values()].some(p => p.trackSid === track);
        if (mine || !activeRef.current) return;
        const id = reader.info.id;
        let text = "";
        speech.current?.({ id, text, done: false });
        for await (const chunk of reader) {
          text += chunk;
          speech.current?.({ id, text, done: false });
        }
        speech.current?.({ id, text, done: true });
      });
      await lk.connect(url, token);
      if (closed) { mic?.stop(); return; }
      if (mic) await lk.localParticipant.publishTrack(mic, { source: Track.Source.Microphone });
      setJoined(lk);
      setState("ready");
    })().catch(error => {
      report({ state: "connect failed", error: String(error?.message || error).slice(0, 300) });
      if (!closed) setState("unavailable");
    });

    return () => {
      closed = true;
      clearTimeout(retry);
      lk?.disconnect();
      setJoined(null);
      setState("off");
      if (!activeRef.current) setWanted(false);  // left while closed: join again on the next tap
    };
  }, [shown, attempt, conversationId, wanted]);

  // Voice mode: microphone on (unless muted), Tuttie's voice audible, levels to the presence.
  useEffect(() => {
    if (!joined) return undefined;
    joined.localParticipant.setMicrophoneEnabled(active && !muted, MIC).catch(() => {});
    // Tells the voice agent whether to speak: with the card closed or typing, Tuttie stays quiet.
    joined.localParticipant.setAttributes({ voice: active ? "on" : "off" }).catch(() => {});
    document.querySelectorAll("audio[data-tuttie]").forEach(el => { el.muted = !active; });
    setState(active ? "live" : "ready");
    if (!active) return undefined;
    const levels = setInterval(() => {
      const tuttie = [...joined.remoteParticipants.values()][0];
      const speaking = Math.min(1, (tuttie?.audioLevel || 0) * 2.5);
      const hearing = Math.min(1, joined.localParticipant.audioLevel * 3);
      levelsTo.current?.(speaking, hearing);
    }, LEVEL_MS);
    return () => {
      clearInterval(levels);
      levelsTo.current?.(0, 0);
    };
  }, [joined, active, muted]);

  /** Browsers may hold back audio until a tap: start Tuttie's voice from one. */
  function unlockAudio() {
    joined?.startAudio().catch(() => {});
  }

  /** Turn the microphone off or on again; Tuttie keeps talking and listening to taps. */
  function toggleMute() {
    setMuted(m => !m);
  }

  return { state, unlockAudio, muted, toggleMute };
}
