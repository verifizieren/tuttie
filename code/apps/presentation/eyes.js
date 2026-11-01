// Tuttie's eyes for the deck: two rounded rectangles that blink gently every ~4 s.
//
// Proportions follow the wallet's open, listening face (apps/wallet/src/lib/face.js, a port of
// pycozmo's procedural face, https://github.com/zayfod/pycozmo, MIT License, Copyright (c)
// 2019-2020): in its 2:1 face box each eye is about 19% wide and 58% high, centred at 30% and
// 70%, with corners of 6.4 of pycozmo's 128x64 units. No code is copied; only the geometry is
// matched (and measured on the live wallet), so the deck's eyes are the same pair, only bigger.

/** The wallet's open eyes (its "listening" look) in a 2:1 face box, in percent. */
export const WALLET_OPEN = { left: [30, 49], right: [70, 49], w: 18.8, h: 58, radius: "27% / 17%" };
/** The deck's big eyes: the same shape as on the wallet's open card. */
export const OPEN = WALLET_OPEN;

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
