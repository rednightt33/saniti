/* The EDGE focus ring (the user 2026-11-27, UD75 "1a", scope "1A": every EDGE page; EXEC.md EXEC-DESIGN-SYSTEM): a focus
   reached with a mouse, a pen or a finger shows no ring; a focus reached with the keyboard shows the design system's one
   neutral grey ring (--focus-ring, .claude/skills/edge-design-system/assets/edge-canonical.css). The browser's own guess
   (:focus-visible) is not enough: Chrome marks a <select> opened with the mouse, and a button given the focus back by
   script after a window was closed with the mouse (the window's own button left the page first), as :focus-visible.

   This module writes the kind of the last input on <html>: data-modality="pointer" on a pointerdown, "keyboard" on a key
   press (a shortcut with Ctrl, Alt or Meta is not a move of the focus and changes nothing). The listeners sit on the
   window in its capture phase, so they run before the page's own handlers and before the example mode's layer
   (shared/example-view.ts) stops an event. The design system turns --focus-ring transparent under "pointer"; before any
   input the attribute is absent and the browser's own guess stands. It keeps no state but the attribute and stores
   nothing. Every page entry imports it (tests/test_focus_ring.py); the shell's copy is static/edge-boot.js. */

export const MODALITY = 'modality';
export type Modality = 'pointer' | 'keyboard';

/** The kind of input a key press is: null for a shortcut with Ctrl, Alt or Meta (it moves no focus). */
export const keyModality = (e: Pick<KeyboardEvent, 'ctrlKey' | 'altKey' | 'metaKey'>): Modality | null =>
  (e.ctrlKey || e.altKey || e.metaKey ? null : 'keyboard');

/** Writes data-modality on the document's <html> from the window's pointer and key events; returns the way to stop. */
export function trackFocusModality(win: Window): () => void {
  const root = win.document.documentElement;
  const set = (m: Modality | null) => { if (m && root.dataset[MODALITY] !== m) root.dataset[MODALITY] = m };
  const pointer = () => set('pointer'), key = (e: KeyboardEvent) => set(keyModality(e));
  win.addEventListener('pointerdown', pointer, true);
  win.addEventListener('keydown', key, true);
  return () => { win.removeEventListener('pointerdown', pointer, true); win.removeEventListener('keydown', key, true) };
}

if (typeof window !== 'undefined' && window.document) trackFocusModality(window);
