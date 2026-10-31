// Voice connection report: when a voice connection fails (or once it works), the wallet tells the
// server what this phone saw, so a failure on a real phone can be understood from the server's
// log (POST /voice/diag). It reports only connection facts: the kinds of network addresses found
// (host, srflx, relay), ICE errors and which relay servers were offered. No audio, no addresses.
let installed = false;

/** Send one report to the server's log (fire and forget). */
export function report(facts) {
  const body = JSON.stringify({ ...facts, agent: navigator.userAgent });
  navigator.sendBeacon?.("/voice/diag", new Blob([body], { type: "application/json" }));
}

/** Watch every WebRTC connection this page makes (once per page). */
export function watchIce() {
  const Native = window.RTCPeerConnection;
  if (installed || !Native) return;
  installed = true;
  function Watched(config, ...rest) {
    const pc = new Native(config, ...rest);
    const kinds = new Set(), errors = [];
    let reported = false;
    pc.addEventListener("icecandidate", e => {
      if (e.candidate?.type) kinds.add(`${e.candidate.type}/${e.candidate.protocol}`);
    });
    pc.addEventListener("icecandidateerror", e => {
      if (errors.length < 8) errors.push(`${e.errorCode} ${e.errorText || ""} ${e.url || ""}`.trim());
    });
    const send = state => {
      if (reported) return;
      reported = true;
      const servers = (pc.getConfiguration().iceServers || []).flatMap(s => [].concat(s.urls));
      report({ state, gathering: pc.iceGatheringState, signaling: pc.signalingState, candidates: [...kinds],
               errors, servers });
    };
    pc.addEventListener("iceconnectionstatechange", () => {
      if (["connected", "completed", "failed"].includes(pc.iceConnectionState)) send(pc.iceConnectionState);
    });
    const close = pc.close.bind(pc);
    pc.close = () => {  // closed before it ever connected: what state was it stuck in?
      send(`closed while ${pc.iceConnectionState}`);
      close();
    };
    return pc;
  }
  Watched.prototype = Native.prototype;
  Object.setPrototypeOf(Watched, Native);  // static methods (e.g. generateCertificate) still work
  window.RTCPeerConnection = Watched;
}
