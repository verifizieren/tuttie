// Procedural agent eyes for Tuttie: a canvas port of pycozmo's procedural face.
//
// Port of pycozmo/procedural_face.py and pycozmo/expressions/expressions.py
// (https://github.com/zayfod/pycozmo, MIT License, Copyright (c) 2019-2020), which is based on
// the "Expressive Eyes" project by Catherine Chambers. A face is the same 43 numbers as in
// pycozmo, drawn with antialiased vector shapes instead of a 128x64 bitmap.
//
// Usage: const face = new TuttieFace(canvas); face.set("happiness"); face.lookAt(x, y);

// ---------- Parameter layout (identical to pycozmo) ----------
// Face: 0 center_x, 1 center_y, 2 scale_x, 3 scale_y, 4 angle. Eyes start at 5 and 24.
const EYE_FIELDS = {
  center_x: 0, center_y: 1, scale_x: 2, scale_y: 3, angle: 4,
  lower_inner_radius_x: 5, lower_inner_radius_y: 6, lower_outer_radius_x: 7, lower_outer_radius_y: 8,
  upper_inner_radius_x: 9, upper_inner_radius_y: 10, upper_outer_radius_x: 11, upper_outer_radius_y: 12,
};
const LID_FIELDS = { y: 0, angle: 1, bend: 2 };  // upper lid at eye + 13, lower lid at eye + 16
const EYE_OFFSETS = [5, 24];

// Design space of pycozmo (the robot's screen); everything is scaled from it.
const W = 128, H = 64;
const EYE_W = 28, EYE_H = 40;
const X_FACTOR = 0.55, Y_FACTOR = 0.25;
const CORNER = W / 20 + H / 10;
const LID_HALF_W = 1.2 * EYE_W, LID_BEND_HALF_W = 1.2 * EYE_W / 2;

function defaultParams() {
  const eye = [0, 0, 1, 1, 0, .5, .5, .5, .5, .5, .5, .5, .5, 0, 0, 0, 0, 0, 0];
  return [0, 0, 1, 1, 0, ...eye, ...eye];
}

// ---------- Expressions (values from pycozmo/expressions/expressions.py) ----------
// Each eye entry sets eye fields; "upper"/"lower" set lid fields. [left eye, right eye].
const both = (left, right) => ({ eyes: [left, right] });
const EXPRESSIONS = {
  neutral: both({ scale_x: .8, scale_y: .8 }, { scale_x: .8, scale_y: .8 }),
  anger: both({ upper: { y: .6, angle: -30 } }, { upper: { y: .6, angle: 30 } }),
  sadness: both({ upper: { y: .6, angle: 20 } }, { upper: { y: .6, angle: -20 } }),
  happiness: both(
    { upper_outer_radius_x: 1, upper_inner_radius_x: 1, lower: { y: .4, bend: .4 } },
    { upper_outer_radius_x: 1, upper_inner_radius_x: 1, lower: { y: .4, bend: .4 } }),
  surprise: both({ scale_x: 1.25, scale_y: 1.25 }, { scale_x: 1.25, scale_y: 1.25 }),
  disgust: both({ upper: { y: .3, angle: 10 }, lower: { y: .3 } }, { upper: { y: .2, angle: 20 }, lower: { y: .2, angle: 10 } }),
  fear: both({ upper: { angle: 30, bend: .1 }, lower: { y: .4, angle: 10 } }, { upper: { angle: -30, bend: .1 }, lower: { y: .4, angle: -10 } }),
  pleading: both({ upper: { angle: 30 }, lower: { y: .5 } }, { upper: { angle: -30 }, lower: { y: .5 } }),
  vulnerability: both({ upper: { angle: 20, y: .3 }, lower: { angle: 10, y: .5 } }, { upper: { angle: -20, y: .3 }, lower: { angle: -10, y: .5 } }),
  despair: both({ upper: { angle: 30, y: .6 } }, { upper: { angle: -30, y: .6 } }),
  guilt: both({ upper: { angle: 10, y: .6, bend: .3 } }, { upper: { angle: -10, y: .6, bend: .3 } }),
  disappointment: both({ upper: { angle: -10, y: .3 }, lower: { y: .4 } }, { upper: { angle: 10, y: .3 }, lower: { y: .4 } }),
  embarrassment: both({ upper: { angle: 10, y: .5, bend: .1 }, lower: { y: .1 } }, { upper: { angle: -10, y: .5, bend: .1 }, lower: { y: .1 } }),
  horror: both({ upper: { angle: 20 } }, { upper: { angle: -20 } }),
  skepticism: both({ upper: { angle: -10, y: .4 } }, { upper: { angle: 25, y: .15 } }),
  annoyance: both(
    { upper: { angle: -30 }, lower: { angle: -10, y: .3 } },
    { upper: { angle: 30, y: .2 }, lower: { angle: 5, y: .4 }, upper_inner_radius_x: 1, upper_outer_radius_x: 1 }),
  fury: both({ upper: { angle: -30, y: .3 }, lower: { y: .4 } }, { upper: { angle: 30, y: .3 }, lower: { y: .4 } }),
  suspicion: both({ upper: { angle: -10, y: .4 }, lower: { y: .5 } }, { upper: { angle: 10, y: .4 }, lower: { y: .5 } }),
  rejection: both({ upper: { angle: 25, y: .8 } }, { upper: { angle: 25, y: .8 } }),
  boredom: both({ upper: { y: .4 } }, { upper: { y: .4 } }),
  tiredness: both({ upper: { angle: 5, y: .4 }, lower: { y: .5 } }, { upper: { angle: -5, y: .4 }, lower: { y: .5 } }),
  asleep: both({ center_y: 50, upper: { y: .45 }, lower: { y: .5 } }, { center_y: 50, upper: { y: .45 }, lower: { y: .5 } }),
  confusion: both({ lower: { y: .2, bend: .2 } }, { upper: { angle: -10, y: .3 }, lower: { angle: 5, y: .2, bend: .2 } }),
  amazement: both({ lower: { y: .2 } }, { lower: { y: .2 } }),
  excitement: both({ lower: { y: .3, bend: .2 } }, { lower: { y: .3, bend: .2 } }),
};

function expressionParams(name) {
  const params = defaultParams();
  const spec = EXPRESSIONS[name];
  if (!spec) throw new Error(`unknown expression ${name}`);
  spec.eyes.forEach((eye, i) => {
    const base = EYE_OFFSETS[i];
    for (const [key, value] of Object.entries(eye)) {
      if (key === "upper" || key === "lower") {
        const lidBase = base + (key === "upper" ? 13 : 16);
        for (const [field, v] of Object.entries(value)) params[lidBase + LID_FIELDS[field]] = v;
      } else {
        params[base + EYE_FIELDS[key]] = value;
      }
    }
  });
  return params;
}

const lerp = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
const easeInOut = t => (t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const rad = deg => (deg * Math.PI) / 180;

// ---------- Rendering ----------
// Rounded eye with an independent elliptical radius per corner (outer = left, inner = right).
function eyePath(ctx, p, e) {
  const r = i => CORNER * p[e + i];
  const x1 = -EYE_W / 2, y1 = -EYE_H / 2, x2 = EYE_W / 2, y2 = EYE_H / 2;
  const [lirx, liry, lorx, lory, uirx, uiry, uorx, uory] = [5, 6, 7, 8, 9, 10, 11, 12].map(r);
  ctx.beginPath();
  ctx.moveTo(x1 + uorx, y1);
  ctx.lineTo(x2 - uirx, y1);
  ctx.ellipse(x2 - uirx, y1 + uiry, uirx, uiry, 0, -Math.PI / 2, 0);
  ctx.lineTo(x2, y2 - liry);
  ctx.ellipse(x2 - lirx, y2 - liry, lirx, liry, 0, 0, Math.PI / 2);
  ctx.lineTo(x1 + lorx, y2);
  ctx.ellipse(x1 + lorx, y2 - lory, lorx, lory, 0, Math.PI / 2, Math.PI);
  ctx.lineTo(x1, y1 + uory);
  ctx.ellipse(x1 + uorx, y1 + uory, uorx, uory, 0, Math.PI, Math.PI * 1.5);
  ctx.closePath();
}

// A lid is a block plus a half-ellipse bend, rotated, that is cut out of the eye.
function cutLid(ctx, p, lidBase, yOffset, angleOffset) {
  const y = p[lidBase], angle = p[lidBase + 1], bend = p[lidBase + 2];
  const lidHeight = EYE_H * y;
  const bendHeight = EYE_H * (1 - y) * bend;
  ctx.save();
  ctx.translate(0, yOffset);
  ctx.rotate(-rad(angle + angleOffset));  // pycozmo (PIL) rotates counter-clockwise
  ctx.beginPath();
  ctx.rect(-LID_HALF_W, -1 - EYE_H / 2, 2 * LID_HALF_W, EYE_H / 2 + lidHeight);
  ctx.moveTo(LID_BEND_HALF_W, -1 + lidHeight);
  ctx.ellipse(0, -1 + lidHeight, LID_BEND_HALF_W, Math.max(bendHeight, 0), 0, 0, Math.PI);
  ctx.fill();
  ctx.restore();
}

class TuttieFace {
  constructor(canvas, { color = "#ffd1bb", glow = "rgba(217, 119, 87, .85)" } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.layer = document.createElement("canvas");  // one eye at a time, so lids never cut the other eye
    this.color = color;
    this.glow = glow;
    this.base = expressionParams("neutral");  // current expression
    this.current = this.base.slice();
    this.from = this.current; this.to = this.current; this.start = 0; this.duration = 1;
    this.gaze = [0, 0];
    this.nextSaccade = 0; this.nextBlink = performance.now() + 2500; this.blinking = 0;
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    requestAnimationFrame(t => this.frame(t));
  }

  /** Change expression by name (see EXPRESSIONS), animated over `ms`. */
  set(name, ms = 450) {
    this.base = expressionParams(name);
    this.animateTo(this.withGaze(this.base), ms);
  }

  /** Look in a direction: x, y in -1..1. */
  lookAt(x, y, ms = 220) {
    this.gaze = [x, y];
    this.animateTo(this.withGaze(this.base), ms);
  }

  withGaze(params) {
    const p = params.slice();
    p[0] += this.gaze[0] * 10;
    p[1] += this.gaze[1] * 40;
    return p;
  }

  animateTo(params, ms) {
    this.from = this.current.slice(); this.to = params; this.start = performance.now(); this.duration = ms;
  }

  resize() {
    const ratio = window.devicePixelRatio || 1;
    const { width, height } = this.canvas.getBoundingClientRect();
    for (const c of [this.canvas, this.layer]) { c.width = Math.max(1, width * ratio); c.height = Math.max(1, height * ratio); }
  }

  frame(now) {
    const t = Math.min(1, (now - this.start) / this.duration);
    this.current = lerp(this.from, this.to, easeInOut(t));
    // Idle life, as in pycozmo's ProceduralFaceGenerator: small saccades and random blinks.
    if (t >= 1 && now > this.nextSaccade) {
      this.nextSaccade = now + 900 + Math.random() * 2600;
      this.lookAt((Math.random() - .5) * .8, (Math.random() - .5) * .5);
    }
    if (now > this.nextBlink) { this.blinking = now; this.nextBlink = now + 2200 + Math.random() * 3800; }
    this.draw(now);
    requestAnimationFrame(next => this.frame(next));
  }

  draw(now) {
    const p = this.current.slice();
    const blink = this.blinking ? Math.min(1, (now - this.blinking) / 180) : 1;
    const closed = 1 - Math.abs(Math.sin(Math.PI * blink));  // 1 open → 0 closed → 1 open
    const { ctx, canvas, layer } = this;
    const lctx = layer.getContext("2d");
    const unit = Math.min(canvas.width / W, canvas.height / H);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    EYE_OFFSETS.forEach((e, i) => {
      lctx.setTransform(1, 0, 0, 1, 0, 0);
      lctx.clearRect(0, 0, layer.width, layer.height);
      // Face transform, then this eye's transform (same order as pycozmo: translate, scale, rotate).
      lctx.translate(canvas.width / 2 + p[0] * X_FACTOR * unit, canvas.height / 2 + p[1] * Y_FACTOR * unit);
      lctx.scale(p[2] * unit, p[3] * unit);
      lctx.rotate(-rad(p[4]));
      lctx.translate(p[e] * X_FACTOR + (i === 0 ? -W / 5 : W / 5), p[e + 1] * Y_FACTOR);
      lctx.scale(p[e + 2], Math.max(p[e + 3] * Math.max(closed, .06), .001));
      lctx.rotate(-rad(p[e + 4]));
      lctx.fillStyle = this.color;
      eyePath(lctx, p, e);
      lctx.fill();
      lctx.globalCompositeOperation = "destination-out";
      cutLid(lctx, p, e + 13, -EYE_H / 2, 0);
      cutLid(lctx, p, e + 16, EYE_H / 2 + 1, 180);
      lctx.globalCompositeOperation = "source-over";
      ctx.save();
      ctx.shadowColor = this.glow;
      ctx.shadowBlur = 8 * unit;
      ctx.drawImage(layer, 0, 0);
      ctx.restore();
    });
  }
}

TuttieFace.EXPRESSIONS = Object.keys(EXPRESSIONS);
window.TuttieFace = TuttieFace;
