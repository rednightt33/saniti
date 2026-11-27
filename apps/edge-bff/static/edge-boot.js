/* EDGE shell, loaded in the head of static/index.html (re-check R2-19: no inline script, so the policy keeps
   script-src 'self' without 'unsafe-inline'). */
/* EXEC-Y (user 2026-10-09: mobile font sizes standardized): the message box uses the text size of the page (14px).
   iOS Safari zooms into a field under 16px when it is tapped; on iOS only, the page keeps its scale (iOS still allows
   pinch zoom). Other devices keep the plain viewport, so their pinch zoom is untouched. */
(() => { const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (ios) document.querySelector('meta[name="viewport"]').setAttribute("content", "width=device-width, initial-scale=1, maximum-scale=1"); })();
/* The EDGE focus ring (the user 2026-11-27, UD75 "1a", scope "1A": every EDGE page), the shell's copy of
   shared/focus-modality.ts (each page's frame runs that one): the kind of the last input on <html>, data-modality=
   "pointer" on a pointerdown, "keyboard" on a key press without Ctrl, Alt or Meta, read in the window's capture phase
   before any handler of the page. The style sheet turns --focus-ring transparent under "pointer", so a focus reached
   with a mouse or a finger, or given back by script after a menu closed with the mouse, shows no ring. */
(() => { const root = document.documentElement, set = m => { if (root.dataset.modality !== m) root.dataset.modality = m; };
  addEventListener("pointerdown", () => set("pointer"), true);
  addEventListener("keydown", e => { if (!e.ctrlKey && !e.altKey && !e.metaKey) set("keyboard"); }, true); })();
