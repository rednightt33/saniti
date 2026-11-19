/* EDGE shell, loaded in the head of static/index.html (re-check R2-19: no inline script, so the policy keeps
   script-src 'self' without 'unsafe-inline'). */
/* EXEC-Y (user 2026-10-09: mobile font sizes standardized): the message box uses the text size of the page (14px).
   iOS Safari zooms into a field under 16px when it is tapped; on iOS only, the page keeps its scale (iOS still allows
   pinch zoom). Other devices keep the plain viewport, so their pinch zoom is untouched. */
(() => { const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (ios) document.querySelector('meta[name="viewport"]').setAttribute("content", "width=device-width, initial-scale=1, maximum-scale=1"); })();
