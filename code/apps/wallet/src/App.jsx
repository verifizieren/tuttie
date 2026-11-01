// The wallet screen: two generic bank cards and the Tuttie card, which is the agent's face.
//
// The agent has three modes:
//   closed  card in the stack, eyes closed (asleep)
//   voice   card open, eyes open; this is the main interface and stays on until the user
//           swipes the card down or switches to typing; taps never send Tuttie away
//   typing  card open with a text field; the eyes close while the user types
//
// Text goes to Tuttie (POST /chat); in voice mode the user simply talks (hooks/useVoice.js,
// code/voice) and Tuttie answers aloud, its answer appearing word by word as it speaks. After a
// typed message Tuttie stays quiet (text only) until the user taps its face or the mic button. What Tuttie does on the agent web arrives on the event
// stream and is shown under its eyes (Activity), including the approval sheet.
//
// There is one conversation at a time: once the user swipes Tuttie down, the next opening
// starts a fresh one, if the current one is over (not while Tuttie works, an approval waits or
// hotel cards wait to be swiped: an accidental swipe down never loses them). The dock under the open
// card shows earlier conversations (kept on this device), starts a new one, or switches to typing.
//
// Tuttie's presence (hooks/usePresence.js) folds all of this into one signal for the eyes: what
// Tuttie is doing (speaking, listening, searching, negotiating, ...), the voice levels and
// one-off cues (an offer, an agreement, a blocked scam). Components below read it with
// usePresenceState / usePresenceEvents; the face gets it at face.onPresence(event) if defined.
import { useCallback, useEffect, useRef, useState } from "react";
import Activity from "./components/Activity.jsx";
import AgentCard from "./components/AgentCard.jsx";
import ApprovalSheet, { ApprovalFallback } from "./components/ApprovalSheet.jsx";
import BankCard from "./components/BankCard.jsx";
import Boundary from "./components/Boundary.jsx";
import Dock from "./components/Dock.jsx";
import History from "./components/History.jsx";
import useAgentStream from "./hooks/useAgentStream.js";
import useFace from "./hooks/useFace.js";
import { PresenceProvider, useFaceDirector, usePresenceSource } from "./hooks/usePresence.js";
import useVisibleViewport from "./hooks/useVisibleViewport.js";
import useVoice from "./hooks/useVoice.js";
import { sendChat } from "./lib/api.js";
import { currentTask } from "./lib/activity.js";
import { serverDecision, sheetOf } from "./lib/approval.js";
import { linkStatus } from "./lib/stream.js";
import { resumeFailure, startsFresh, viewedChat } from "./lib/history.js";
import { bookingRequest } from "./lib/picks.js";
import { clearsOnReconnect, newChatFailure, PICK_UNREACHABLE, shouldResend, voiceNote } from "./lib/recovery.js";

// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const OPEN_GUARD_MS = 700;
const REVEAL_WAIT_MS = 3000;  // no speech for a new answer by then: show it in full at once
const CLOSE_AFTER_MS = 900;  // after the goodbye: a moment to read it before the card closes
const RESEND_MS = 1500;  // a message that did not reach Tuttie is sent once more after this
const DECIDE_FIRST = "Decide on the booking first";
const DECISION_ON_ITS_WAY = "One moment, your decision is on its way";
const NOTICE_MS = 4000;  // a friendly note under the eyes (e.g. "still working") goes after this


export default function App() {
  const [mode, setMode] = useState("closed");
  const [error, setError] = useState("");  // the only text under the eyes: Tuttie cannot be reached
  const [notice, setNotice] = useState("");  // a short friendly note that is not an error; clears itself
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const closedOnce = useRef(false);  // the user swiped Tuttie down: the next opening starts fresh
  const face = useFace(canvas);
  const [agent, actions, history, lastChange, switching, connectionError, link, opened, lost] = useAgentStream();
  // An approval the server no longer knows (already decided or expired): the sheet said so and
  // went; the wallet stops waiting for it even if no event about it arrives.
  const [goneApproval, setGoneApproval] = useState(null);
  const approval = agent.approval && agent.approval.id !== goneApproval ? agent.approval : null;
  // A decided approval stays on screen until its sheet has shown the final mark (the Face ID
  // checkmark or the X) and slid away, even though the server already stopped waiting for it;
  // a newer approval (the city tax right after the booking) is shown after it.
  const [finishing, setFinishing] = useState(null);
  const sheetApproval = sheetOf(approval, finishing);
  const approvalId = sheetApproval?.id;
  const dropApproval = useCallback(() => { setGoneApproval(approvalId); setFinishing(null); }, [approvalId]);
  // Only the sheet that is finishing clears it: a late finish of an older sheet leaves a newer one.
  // A decided approval is over for the wallet once its sheet finished, even if the event saying so
  // never arrived (a dropped stream): it is not shown again and does not block New chat.
  const sheetDone = useCallback((id, decided) => {
    setFinishing(f => (f && f.id !== id ? f : null));
    if (decided) setGoneApproval(id);
  }, []);
  const [showHistory, setShowHistory] = useState(false);
  // The past chat open in the history (null = the list), why it could not be continued, and
  // whether it is being restored.
  const [historyChat, setHistoryChat] = useState({ id: null, error: "", resuming: false });
  const [quiet, setQuiet] = useState(false);  // the user typed: Tuttie answers in text only
  // A new answer in voice mode: shown as Tuttie speaks it ({ answer, id, text } while revealing).
  const [reveal, setReveal] = useState(null);
  // What Tuttie is doing, and the eyes following it (lib/presence.js, lib/faceDirector.js).
  const presence = usePresenceSource({ mode, agent, error, lastChange }, face);
  useFaceDirector(presence, face);
  const { state: voice, unlockAudio, muted, micBlocked, toggleMute, retry: retryVoice } = useVoice(mode === "voice" && !quiet && !switching, onSpeech,
                                                                    presence.levels, agent.id);

  // Only a speech stream that starts after the answer arrived is the answer being read out.
  function onSpeech({ id, text, done }) {
    setReveal(r => {
      if (!r || (r.id && r.id !== id)) return r;
      if (done) return null;  // spoken to the end: show the whole answer with its formatting
      return { ...r, id, text };
    });
  }

  useEffect(() => {
    if (!agent.answer || voice !== "live") return setReveal(null);
    setReveal({ answer: agent.answer, id: null, text: "" });
    const fallback = setTimeout(() => setReveal(r => (r && !r.id ? null : r)), REVEAL_WAIT_MS);
    return () => clearTimeout(fallback);
  }, [agent.answer]);  // eslint-disable-line react-hooks/exhaustive-deps
  // The user said goodbye (Tuttie's end_conversation): once the goodbye is shown and spoken, the
  // card closes itself, as if swiped down.
  useEffect(() => {
    if (agent.closing !== "ready" || reveal || mode === "closed" || sheetApproval) return undefined;  // never away from an approval sheet
    const timer = setTimeout(close, CLOSE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [agent.closing, reveal, mode, sheetApproval]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(""), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);
  // "Tuttie is unreachable" from a failed send goes once the stream has connected again.
  useEffect(() => {
    if (opened) setError(e => (clearsOnReconnect(e) ? "" : e));
  }, [opened]);
  useVisibleViewport();
  const busy = Boolean(agent.turns.length || agent.request);

  function startVoice() {
    unlockAudio();
    setQuiet(false);
    if (mode === "closed") {
      openedAt.current = performance.now();
      if (closedOnce.current && !approval && startsFresh(agent)) {
        actions.newConversation(agent).then(() => setError(""), failedNewChat);  // an old error never outlives it
      }
      closedOnce.current = false;
    }
    setMode("voice");
  }

  function close() {
    setMode("closed");
    setShowHistory(false);
    closedOnce.current = true;
  }

  // A new conversation from the dock: the current one goes into the history.
  async function newChat() {
    setShowHistory(false);
    // Never a new chat under the sheet: a decision on its way finishes first, a waiting one needs the user.
    if (finishing) return setNotice(DECISION_ON_ITS_WAY);
    if (approval) return setNotice(DECIDE_FIRST);
    try {
      await actions.newConversation(agent);
      setError("");
      presence.cue("new_chat");
    } catch (e) { failedNewChat(e); }
  }

  // Tuttie still works on an answer (409): a note that goes by itself, not an error.
  function failedNewChat(e) {
    const { notice: note, error: reason } = newChatFailure(e);
    if (note) setNotice(note);
    else setError(reason);
  }

  function tapWhileOpen() {
    unlockAudio();
    setQuiet(false);  // tapping Tuttie's face brings its voice back after typing
    if (mode !== "voice") return startVoice();  // voice mode starting again also retries voice
    retryVoice();  // voice could not connect: the tap tries again
    presence.cue("tap");  // a tap never ends voice mode, Tuttie just reacts
  }

  // The dock's History button always shows the list, also from inside a past chat.
  function openHistory() {
    if (finishing) return setNotice(DECISION_ON_ITS_WAY);  // the sheet covers the card: never open the history under it
    if (approval) return setNotice(DECIDE_FIRST);
    setHistoryChat({ id: null, error: "", resuming: false });
    setShowHistory(true);
  }

  // Continue a past chat: the server restores that conversation first; only then does the card
  // show it (in voice or typing). If it expired, the history says so and nothing else changes.
  async function resumeChat(entry, then) {
    if (historyChat.resuming) return;
    setHistoryChat({ id: entry.id, error: "", resuming: true });
    try {
      await actions.resume(entry);
    } catch (e) {
      return setHistoryChat({ id: entry.id, error: resumeFailure(e), resuming: false });
    }
    setHistoryChat({ id: null, error: "", resuming: false });
    setShowHistory(false);
    setError("");
    if (then === "voice") setQuiet(false);
    setMode(then);
  }

  // The keyboard types into the chat on screen: a past chat open in the history is resumed first.
  function startTyping() {
    if (performance.now() - openedAt.current <= OPEN_GUARD_MS) return;
    const viewed = showHistory && viewedChat(history, historyChat.id, agent.id);
    if (viewed) return resumeChat(viewed, "typing");
    setShowHistory(false);
    setMode("typing");
  }

  // An approval needs the user: open the card if it is closed.
  useEffect(() => {
    if (approval && mode === "closed") startVoice();
  }, [approval]);  // eslint-disable-line react-hooks/exhaustive-deps

  // `shown` is what the history keeps of the user's words; `text` is what Tuttie gets. A typed
  // message makes Tuttie answer quietly, in text only. With `resend`, a message that did not
  // reach Tuttie (network, server failure; never a refusal) is sent once more by itself.
  // Returns whether Tuttie got it.
  async function send(text, firstTool = null, shown = text, typed = false, resend = false) {
    if (switching) {
      setError("Please wait for the conversation to load");
      return false;
    }
    // Not connected: reconnect now, and still try to send; the server refuses (409) a message
    // for a chat it no longer has, and a failed send keeps the typed text in the field.
    if (connectionError) actions.retry();
    if (typed) setQuiet(true);
    actions.say(shown);
    setShowHistory(false);
    setMode("voice");  // Tuttie is awake while it works
    setError("");
    for (let tries = 1; ; tries++) {
      try {
        const { turn_id: turnId } = await sendChat(text, firstTool, agent.id, shown);
        actions.sent(shown, turnId);
        return true;
      } catch (e) {
        if (!resend || tries > 1 || !shouldResend(e)) {
          actions.failed(shown, e);  // not sent: it must not hold the place of the next request's answer
          if (typed) setMode("typing");  // back to the field, where the text waits to be sent again
          setError(e.status === 409 ? "The chat changed elsewhere. Showing the current one, please say it again."
                                    : e.message || "Tuttie is unreachable right now");
          return false;
        }
        await new Promise(resolve => setTimeout(resolve, RESEND_MS));
      }
    }
  }

  // The user swiped through the cards: book the best liked deal (the lowest agreed price; a card
  // without any price comes last); the
  // other liked hotels are named so Tuttie can offer the next one after a decline (lib/picks.js).
  // If the choice cannot reach Tuttie (even after one more try), the cards come back, so
  // swiping again sends it again.
  async function pick(liked) {
    const { best, text, shown } = bookingRequest(liked);
    actions.pick([best.node_id]);
    const sent = await send(text, "book", shown, false, true);
    if (sent) return;
    actions.pick(null);
    setError(PICK_UNREACHABLE);
  }

  // While a hotel card is dragged, Tuttie looks the same way (the face director follows `lean`).
  function lean(x) {
    presence.update({ lean: x });
  }

  const classes = ["app", mode !== "closed" && "open", mode === "voice" && "voice", mode === "typing" && "typing",
                   busy && "busy"];
  return (
    <PresenceProvider value={presence}>
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="head"><h1>Wallet</h1></div>
      <BankCard index={0} color="blue" />
      <BankCard index={1} color="black" />
      <AgentCard canvasRef={canvas} mode={mode} status={error || connectionError || lost || notice || (switching ? "Loading conversation…" : linkStatus(link) || currentTask(agent))
                                                     || (mode === "voice" && !quiet ? voiceNote(voice, micBlocked) : "")}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen} onSend={text => send(text, null, text, true)}>
        <Boundary key={agent.id} message="Something went wrong showing this chat. Start a new chat from the dock.">
          <Activity state={agent} onPick={switching ? undefined : pick} onLean={lean} onDeck={actions.deck} reveal={reveal} />
        </Boundary>
        {showHistory && <Boundary key={historyChat.id || "list"} className="history"
                                   message="This earlier chat cannot be shown. Tap History in the dock to go back.">
          <History entries={history.filter(e => e.id !== agent.id)} open={historyChat.id}
            error={historyChat.error} resuming={historyChat.resuming} onClose={() => setShowHistory(false)}
            onOpen={id => setHistoryChat({ id, error: "", resuming: false })}
            onResume={() => resumeChat(history.find(e => e.id === historyChat.id), "voice")} />
        </Boundary>}
        {sheetApproval && <Boundary key={approvalId} fallback={<ApprovalFallback approval={sheetApproval} onGone={() => { dropApproval(); sheetDone(); }} />}>
          <ApprovalSheet approval={sheetApproval} onGone={dropApproval} note={notice} recorded={serverDecision(agent, approvalId)}
                         onDecide={setFinishing} onFinished={sheetDone} />
        </Boundary>}
      </AgentCard>
      <Dock onHistory={openHistory} onNewChat={newChat} onKeyboard={startTyping}
            muted={muted || quiet} blocked={micBlocked && voice !== "disabled"} onMute={quiet ? () => setQuiet(false) : toggleMute} />
    </div>
    </PresenceProvider>
  );
}
