// Touch gestures for the Tuttie card, in the style of an iOS sheet.
//
// - The card follows the finger once per animation frame (pointer capture keeps it attached
//   even when the finger leaves the card).
// - On release, the decision uses the speed of the last ~100 ms, not of the whole gesture, so
//   an uneven swipe, a quick flick or a flick back are all read the way the user meant them.
// - The closing or spring-back animation starts from where the finger let go (no jump) and
//   its duration matches the finger's speed.
// - Closed: a tap or a swipe up opens. Open: a swipe down closes, a swipe left or right is
//   passed on (new conversation, history). Pulling the "wrong" way moves the card a little
//   with rubber-band resistance.
// - Touches inside a scrolling area ([data-scroll], [data-hscroll]) belong to that area: the
//   browser scrolls it natively and the card never moves or closes from there.
import { useEffect, useRef } from "react";

const TAP_PX = 8;             // a finger may move this much and still count as a tap
const SAMPLE_MS = 100;        // window used for the release speed
const CLOSE_PX = 120;         // released this far down, the open card closes
const FLICK_PX = 30;          // ...or this far, if the finger was still moving fast
const FLICK_SPEED = 0.35;     // px per ms that counts as a flick (≈ 350 px/s)
const OPEN_PX = 30;           // swipe-up distance that opens the closed card
const SIDE_PX = 70;           // sideways distance (or a flick) that counts as a swipe left or right
const OWN_GESTURES = "button, form, input, label, [data-scroll], [data-hscroll]";

// Past the natural direction the card moves less and less, like a rubber band.
const rubber = (d, k = 4) => Math.sign(d) * Math.sqrt(Math.abs(d)) * k;

/**
 * @param cardRef  ref to the card element
 * @param isOpen   () => boolean, read at gesture time
 * @param onOpen   called for a tap or swipe up on the closed card
 * @param onClose  called for a swipe down on the open card
 * @param onTap    called for a tap on the open card
 * @param onSwipe  called with "left" or "right" for a sideways swipe on the open card
 */
export default function useCardGestures(cardRef, { isOpen, onOpen, onClose, onTap, onSwipe }) {
  // Keep the latest callbacks without re-binding the listeners on every render.
  const handlers = useRef({ isOpen, onOpen, onClose, onTap, onSwipe });
  handlers.current = { isOpen, onOpen, onClose, onTap, onSwipe };

  useEffect(() => {
    const card = cardRef.current;
    let drag = null;  // { startX, startY, axis, samples: [{ x, y, t }], offset, frame }

    const offsetFor = dy => (handlers.current.isOpen()
      ? (dy > 0 ? dy : rubber(dy))                              // open: down follows 1:1
      : (dy < 0 ? Math.max(rubber(dy, 6), -90) : rubber(dy, 2))); // closed: up, with resistance

    function paint() {
      drag.frame = null;
      // The card keeps its shape, it only moves: down/up, or a little sideways with resistance.
      card.style.transform = drag.axis === "x" ? `translateX(${drag.offset}px)` : `translateY(${drag.offset}px)`;
    }

    // Run the next CSS transition at `ms`, then fall back to the duration from the stylesheet.
    function settleIn(ms) {
      card.style.transitionDuration = `${ms}ms`;
      setTimeout(() => card.style.removeProperty("transition-duration"), ms + 50);
    }

    function down(e) {
      if (e.target.closest(OWN_GESTURES) || drag) return;
      try { card.setPointerCapture(e.pointerId); } catch { /* not every pointer can be captured */ }
      drag = { startX: e.clientX, startY: e.clientY, axis: null, offset: 0, frame: null,
               samples: [{ x: e.clientX, y: e.clientY, t: performance.now() }] };
    }

    function move(e) {
      if (!drag) return;
      const now = performance.now();
      drag.samples.push({ x: e.clientX, y: e.clientY, t: now });
      while (drag.samples.length > 2 && now - drag.samples[0].t > SAMPLE_MS) drag.samples.shift();
      const dx = e.clientX - drag.startX, dy = e.clientY - drag.startY;
      if (!drag.axis) {
        if (Math.hypot(dx, dy) < TAP_PX) return;
        // Sideways only on the open card; the closed card in the stack only moves up and down.
        drag.axis = Math.abs(dx) > Math.abs(dy) && handlers.current.isOpen() ? "x" : "y";
      }
      card.classList.add("dragging");
      drag.offset = drag.axis === "x" ? Math.max(-60, Math.min(60, rubber(dx, 5))) : offsetFor(dy);
      if (!drag.frame) drag.frame = requestAnimationFrame(paint);
    }

    function up(e) {
      if (!drag) return;
      if (drag.frame) cancelAnimationFrame(drag.frame);
      const first = drag.samples[0], elapsed = Math.max(16, performance.now() - first.t);
      const sideways = drag.axis === "x", moved = sideways ? e.clientX - drag.startX : e.clientY - drag.startY;
      const speed = (sideways ? e.clientX - first.x : e.clientY - first.y) / elapsed;  // px/ms, + = down/right
      const dragged = card.classList.contains("dragging"), open = handlers.current.isOpen();
      drag = null;

      let action = null;
      if (!dragged || Math.abs(moved) < TAP_PX) action = "tap";
      else if (sideways && (Math.abs(moved) > SIDE_PX || Math.abs(speed) > FLICK_SPEED)) action = moved < 0 ? "left" : "right";
      else if (open && speed > -0.2 && (moved > CLOSE_PX || (moved > FLICK_PX && speed > FLICK_SPEED))) action = "close";
      else if (!open && speed < 0.2 && (moved < -OPEN_PX || speed < -FLICK_SPEED)) action = "open";

      // Fast flicks finish fast, slow drags settle softly; a tap keeps the stylesheet's timing.
      if (action !== "tap" && !sideways) {
        const remaining = action === "close" ? Math.max(200, window.innerHeight - moved) : Math.abs(moved) + 60;
        settleIn(Math.round(Math.min(650, Math.max(240, remaining / Math.max(Math.abs(speed), 0.8)))));
      }
      card.classList.remove("dragging");
      card.style.removeProperty("transform");  // transitions back from the dragged position

      if (action === "close") handlers.current.onClose();
      else if (action === "open") handlers.current.onOpen();
      else if (action === "tap") (open ? handlers.current.onTap : handlers.current.onOpen)();
      else if (action === "left" || action === "right") handlers.current.onSwipe?.(action);
    }

    // The browser took over the touch (e.g. to scroll): just let go, no tap, no swipe.
    function cancel() {
      if (!drag) return;
      if (drag.frame) cancelAnimationFrame(drag.frame);
      drag = null;
      card.classList.remove("dragging");
      card.style.removeProperty("transform");
    }

    card.addEventListener("pointerdown", down);
    card.addEventListener("pointermove", move);
    card.addEventListener("pointerup", up);
    card.addEventListener("pointercancel", cancel);
    return () => {
      card.removeEventListener("pointerdown", down);
      card.removeEventListener("pointermove", move);
      card.removeEventListener("pointerup", up);
      card.removeEventListener("pointercancel", cancel);
    };
  }, [cardRef]);
}
