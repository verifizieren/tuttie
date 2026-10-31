// The bar under the open Tuttie card: earlier conversations, a new conversation, and the
// keyboard (typing is a deliberate choice; voice is the main interface).

function HistoryIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6M3.5 4.5V9H8M12 7.5V12l3 2" />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 20.5h7.5M16 4.5l3.5 3.5L9 18.5l-4.5 1 1-4.5z" />
    </svg>
  );
}

function KeyboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <rect x="2.5" y="6" width="19" height="12" rx="2.5" />
      <path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M7.5 14h9" />
    </svg>
  );
}

/**
 * @param onHistory   show earlier conversations
 * @param onNewChat   start a new conversation (the current one goes into the history)
 * @param onKeyboard  switch to typing
 */
export default function Dock({ onHistory, onNewChat, onKeyboard }) {
  return (
    <nav className="dock" aria-label="Tuttie">
      <button type="button" onClick={onHistory} aria-label="History"><HistoryIcon /></button>
      <button type="button" onClick={onNewChat} aria-label="New chat"><NewChatIcon /></button>
      <button type="button" onClick={onKeyboard} aria-label="Type instead"><KeyboardIcon /></button>
    </nav>
  );
}
