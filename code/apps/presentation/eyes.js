// Tuttie's eyes for the deck: two rounded rectangles that blink gently every ~4 s.
//
// Proportions follow the wallet's face (apps/wallet/src/lib/face.js, a port of pycozmo's
// procedural face, https://github.com/zayfod/pycozmo, MIT License, Copyright (c) 2019-2020):
// in a 2:1 face box each eye is 17.5% wide and 50% high, centred at 34% and 66%, with corner
// radii of 23% of its width. No code is copied; only the geometry is matched so the deck's
// eyes land exactly on the wallet's Tuttie card.

/** Open-eye geometry in the face box, in percent. */
export const OPEN = { left: [34, 50], right: [66, 50], w: 17.5, h: 50, radius: "23% / 16%" };
/** The wallet's sleeping eyes (closed bars) in the same box, measured from the live wallet. */
export const ASLEEP = { left: [30.1, 68.6], right: [70.2, 68.6], w: 21.9, h: 7.9, radius: "2px" };

/** Inline style for one eye in a pose. */
export function eyeStyle(pose, side) {
  const [cx, cy] = pose[side];
  return {
    left: `${cx - pose.w / 2}%`, top: `${cy - pose.h / 2}%`,
    width: `${pose.w}%`, height: `${pose.h}%`, borderRadius: pose.radius,
  };
}

/** Fill `box` with two eyes and start blinking. Returns { eyes, stop }. */
export function createFace(box) {
  const eyes = ["left", "right"].map(side => {
    const eye = document.createElement("i");
    eye.className = `eye ${side}`;
    Object.assign(eye.style, eyeStyle(OPEN, side));
    box.append(eye);
    return eye;
  });
  let timer = 0;
  const blink = () => {
    // Skip when hidden: nothing should move off screen.
    if (box.offsetParent !== null && getComputedStyle(box).opacity !== "0") {
      for (const eye of eyes) {
        eye.animate(
          [{ transform: "scaleY(1)" }, { transform: "scaleY(.06)", offset: .5 }, { transform: "scaleY(1)" }],
          { duration: 200, easing: "ease-in-out" });
      }
    }
    timer = setTimeout(blink, 3400 + Math.random() * 1400);
  };
  timer = setTimeout(blink, 1600);
  return { eyes, stop: () => clearTimeout(timer) };
}
