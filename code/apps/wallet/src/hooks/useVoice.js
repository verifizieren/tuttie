// Tuttie's voice in the wallet: while voice mode is on, join this conversation's LiveKit room
// (token from POST /voice/token), send the microphone, play Tuttie's voice, and pass both voice
// levels to the face, so its eyes pulse while Tuttie speaks and open up while the user talks.
// Speech becomes a message to the same Tuttie as typing (code/voice/agent.py); without voice
// configured on the server the wallet simply stays text-only. What Tuttie says also arrives
// as text, word by word in step with its voice (LiveKit's "lk.transcription" streams), so the
// wallet can show an answer as it is spoken.
import { useEffect, useRef, useState } from "react";

const LEVEL_MS = 50;  // how often the voice levels go to the face
// The phone's own clean-up of the microphone: background noise and Tuttie's own voice are
// filtered before anything is sent; voice isolation (e.g. on iPhones) is the stronger form.
const MIC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, voiceIsolation: true };

/**
 * @param active  voice mode is on (the card is open and the user is not typing)
 * @param face    ref to the TuttieFace (src/lib/face.js)
 * @param onSpeech  ({ id, text, done }) => void: Tuttie's words so far, as it speaks them
 * @param onLevels  (speaking, hearing) => void: both voice levels (0..1), every LEVEL_MS while live,
 *                  and (0, 0) when voice stops; feeds Tuttie's presence (hooks/usePresence.js)
 * @returns { state, unlockAudio, muted, toggleMute }: state is "off" | "connecting" | "live" |
 *          "unavailable"; call unlockAudio() from a tap if the browser blocked Tuttie's voice;
 *          muted keeps the microphone off (e.g. in a noisy room) until toggled again
 */
export default function useVoice(active, face, onSpeech, onLevels) {
  const speech = useRef(onSpeech);
  speech.current = onSpeech;
  const levelsTo = useRef(onLevels);
  levelsTo.current = onLevels;
  const [state, setState] = useState("off");
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(false);
  const room = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    let closed = false, levels = null, lk = null;
    setState("connecting");
    (async () => {
      // LiveKit is loaded only when voice starts, so the wallet itself opens fast.
      const { Room, RoomEvent, Track } = await import("livekit-client");
      if (closed) return;
      lk = new Room({ adaptiveStream: true, dynacast: true });
      room.current = lk;
      lk.on(RoomEvent.TrackSubscribed, track => {
        if (track.kind !== Track.Kind.Audio) return;
        const audio = track.attach();  // Tuttie's voice
        audio.hidden = true;
        document.body.appendChild(audio);
      });
      lk.on(RoomEvent.TrackUnsubscribed, track => track.detach().forEach(el => el.remove()));
      // Tuttie's words, in step with its voice. The user's own words come on the same topic,
      // marked with the user's microphone track: those are skipped.
      lk.registerTextStreamHandler("lk.transcription", async reader => {
        const track = reader.info.attributes?.["lk.transcribed_track_id"];
        const mine = [...lk.localParticipant.trackPublications.values()].some(p => p.trackSid === track);
        if (mine) return;
        const id = reader.info.id;
        let text = "";
        speech.current?.({ id, text, done: false });
        for await (const chunk of reader) {
          text += chunk;
          speech.current?.({ id, text, done: false });
        }
        speech.current?.({ id, text, done: true });
      });
      const response = await fetch("/voice/token", { method: "POST" });
      if (!response.ok) throw new Error("voice is not configured");
      const { url, token } = await response.json();
      await lk.connect(url, token);
      if (closed) return;
      await lk.localParticipant.setMicrophoneEnabled(!mutedRef.current, MIC);
      setState("live");
      levels = setInterval(() => {
        const tuttie = [...lk.remoteParticipants.values()][0];
        const speaking = Math.min(1, (tuttie?.audioLevel || 0) * 2.5), hearing = Math.min(1, lk.localParticipant.audioLevel * 3);
        face.current?.setVoice(speaking, hearing);
        levelsTo.current?.(speaking, hearing);
      }, LEVEL_MS);
    })().catch(() => !closed && setState("unavailable"));

    return () => {
      closed = true;
      clearInterval(levels);
      face.current?.setVoice(0, 0);
      levelsTo.current?.(0, 0);
      lk?.disconnect();
      room.current = null;
      setState("off");
    };
  }, [active, face]);

  /** Browsers may hold back audio until a tap: start Tuttie's voice from one. */
  function unlockAudio() {
    room.current?.startAudio().catch(() => {});
  }

  /** Turn the microphone off or on again; Tuttie keeps talking and listening to taps. */
  function toggleMute() {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    room.current?.localParticipant.setMicrophoneEnabled(!next, MIC).catch(() => {});
  }

  return { state, unlockAudio, muted, toggleMute };
}
