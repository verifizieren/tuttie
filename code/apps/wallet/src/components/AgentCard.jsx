// The Tuttie card: the agent's face on a dark card, a quiet name label, and (when open) a grab
// bar, what Tuttie is doing (children: activity, approval sheet) and the controls. Gestures
// (tap, swipe up, swipe down, swipe left or right) come from useCardGestures.
import { useRef } from "react";
import useCardGestures from "../hooks/useCardGestures.js";
import AgentControls from "./AgentControls.jsx";

/**
 * @param canvasRef  ref for the face canvas (drawn by useFace in the parent)
 * @param mode       "closed" | "voice" | "typing"
 * @param onOpen     tap or swipe up on the closed card
 * @param onClose    swipe down on the open card
 * @param onTap      tap on the open card
 * @param onSwipe    "left" or "right" swipe on the open card
 * Other props are passed on to AgentControls.
 */
export default function AgentCard({ canvasRef, mode, onOpen, onClose, onTap, onSwipe, children, ...controls }) {
  const card = useRef(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useCardGestures(card, { isOpen: () => modeRef.current !== "closed", onOpen, onClose, onTap, onSwipe });

  return (
    <div ref={card} className="card agent" style={{ "--i": 2 }} aria-label="Tuttie, tap to talk">
      <canvas ref={canvasRef} />
      <div className="edge" />
      <div className="grabber" />
      <span className="label">Tuttie</span>
      {children}
      <AgentControls mode={mode} {...controls} />
    </div>
  );
}
