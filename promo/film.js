// A tiny timeline for the promo films. Nothing moves by itself: render.py calls
// window.seek(t) for every frame, and each scene sets its elements' styles from t,
// so every frame is the same on every run.
"use strict";

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
// 0 before a, 1 after b, the share of the way in between.
const p = (t, a, b) => clamp((t - a) / (b - a));
const lerp = (a, b, x) => a + (b - a) * x;
const ease = {
  out: (x) => 1 - Math.pow(1 - x, 3),
  in: (x) => x * x * x,
  inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  back: (x) => 1 + 2.4 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2),
  soft: (x) => 1 - Math.pow(1 - x, 2),
};
const $ = (id) => document.getElementById(id);

// Fade in over [a, a+d], out over [b-d, b]; with a rise of `rise` px while it comes in.
function show(el, t, a, b, { d = 0.45, rise = 24, scale = 0, out = true } = {}) {
  if (typeof el === "string") el = $(el);
  const inn = ease.out(p(t, a, a + d));
  const gone = out ? ease.in(p(t, b - d, b)) : 0;
  const o = inn * (1 - gone);
  el.style.opacity = o.toFixed(3);
  el.style.visibility = o > 0.001 ? "visible" : "hidden";
  const y = (1 - inn) * rise - gone * rise * 0.5;
  const s = 1 - (1 - inn) * scale - gone * scale * 0.5;
  el.style.transform = `translateY(${y.toFixed(2)}px) scale(${s.toFixed(4)})`;
  return o;
}

// Text typed between a and b.
function type(el, text, t, a, b) {
  if (typeof el === "string") el = $(el);
  const n = Math.round(text.length * p(t, a, b));
  el.textContent = text.slice(0, n);
  return n === text.length;
}

// A path of [time, x, y] points, eased between them.
function along(points, t) {
  if (t <= points[0][0]) return points[0].slice(1);
  for (let i = 1; i < points.length; i++) {
    const [t1, x1, y1] = points[i];
    const [t0, x0, y0] = points[i - 1];
    if (t <= t1) {
      const k = ease.inOut(p(t, t0, t1));
      return [lerp(x0, x1, k), lerp(y0, y1, k)];
    }
  }
  return points[points.length - 1].slice(1);
}

// A pointer that follows a path; clicks are [time, ...] (the pointer dips, a ring grows).
function pointer(el, ring, points, clicks, t, visible) {
  const [x, y] = along(points, t);
  const pressed = clicks.some((c) => t >= c && t < c + 0.14);
  el.style.opacity = visible ? "1" : "0";
  el.style.transform = `translate(${x}px, ${y}px) scale(${pressed ? 0.86 : 1})`;
  const last = clicks.filter((c) => t >= c).pop();
  const k = last === undefined ? 1 : p(t, last, last + 0.5);
  ring.style.opacity = visible && k < 1 ? (0.55 * (1 - k)).toFixed(3) : "0";
  ring.style.transform = `translate(${x}px, ${y}px) scale(${0.3 + k * 1.4})`;
}

// Count up from a to b between t0 and t1.
const count = (t, t0, t1, a, b) => Math.round(lerp(a, b, ease.inOut(p(t, t0, t1))));

window.FILM = window.FILM || { fps: 30, duration: 10, width: 1080, height: 1350 };
const SCENES = [];
window.seek = (t) => {
  for (const scene of SCENES) scene(t);
};
