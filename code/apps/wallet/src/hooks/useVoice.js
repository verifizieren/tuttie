// Tuttie's voice in the wallet: while voice mode is on, join this conversation's LiveKit room
// (token from POST /voice/token), send the microphone, play Tuttie's voice, and pass both voice
// levels to the face, so its eyes pulse while Tuttie speaks and open up while the user talks.
// Speech becomes a message to the same Tuttie as typing (code/voice/agent.py); without voice
// configured on the server the wallet simply stays text-only.
import { useEffect, useRef, useState } from "react";

const LEVEL_MS = 50;  // how often the voice levels go to the face
// The phone's own clean-up of the microphone: background noise and Tuttie's own voice are
// filtered before anything is sent; voice isolation (e.g. on iPhones) is the stronger form.
const MIC = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, voiceIsolation: true };

/**
 * @param active  voice mode is on (the card is open and the user is not typing)
 * @param face    ref to the TuttieFace (src/lib/face.js)
 * @returns { state, unlockAudio, muted, toggleMute }: state is "off" | "connecting" | "live" |
 *          "unavailable"; call unlockAudio() from a tap if the browser blocked Tuttie's voice;
 *          muted keeps the microphone off (e.g. in a noisy room) until toggled again
 */
export default function useVoice(active, face) {
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
      const response = await fetch("/voice/token", { method: "POST" });
      if (!response.ok) throw new Error("voice is not configured");
      const { url, token } = await response.json();
      await lk.connect(url, token);
      if (closed) return;
      await lk.localParticipant.setMicrophoneEnabled(!mutedRef.current, MIC);
      setState("live");
      levels = setInterval(() => {
        const tuttie = [...lk.remoteParticipants.values()][0];
        face.current?.setVoice((tuttie?.audioLevel || 0) * 2.5, lk.localParticipant.audioLevel * 3);
      }, LEVEL_MS);
    })().catch(() => !closed && setState("unavailable"));

    return () => {
      closed = true;
      clearInterval(levels);
      face.current?.setVoice(0, 0);
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
