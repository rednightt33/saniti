// EXEC-TERMINAL-LAG-2 U1 (user 2026-11-22: "U1 + U2 + U4 go"): the indicators that follow the view are computed again
// once the view has settled, never while a pointer is still held (src/app/viewFollow.ts). With the CPU four times slower
// the 150 ms quiet rule alone fired in the middle of a drag (frames more than 150 ms apart): 1 to 8 recomputes of 1-1.7 s.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { followPointer, viewFollower } from '../../src/app/viewFollow';

describe('viewFollower', () => {
  beforeEach(() => { vi.useFakeTimers() });
  afterEach(() => { vi.useRealTimers() });

  it('a wheel or key move settles 150 ms after the last move, once', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.moved(); vi.advanceTimersByTime(100); f.moved(); vi.advanceTimersByTime(149);
    expect(settle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1); expect(settle).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(5000); expect(settle).toHaveBeenCalledTimes(1);
  });
  it('a drag with frames 200-400 ms apart (a slow CPU) never settles before the release', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.down();
    for (let k = 0; k < 40; k++) { f.moved(); vi.advanceTimersByTime(200 + (k % 3) * 100) }
    expect(settle).not.toHaveBeenCalled();
    f.up(); vi.advanceTimersByTime(149); expect(settle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1); expect(settle).toHaveBeenCalledTimes(1);
  });
  it('a touch glide after the release keeps moving the view: it settles after the glide', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.down(); f.moved(); f.up();
    for (let k = 0; k < 10; k++) { vi.advanceTimersByTime(16); f.moved() }
    expect(settle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(150); expect(settle).toHaveBeenCalledTimes(1);
  });
  it('a pointer still held without a move for 1 s settles (the user stopped; a release outside the frame)', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.down(); f.moved(); vi.advanceTimersByTime(999); expect(settle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1); expect(settle).toHaveBeenCalledTimes(1);
  });
  it('a click or a release with no move does not compute', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.down(); f.up(); vi.advanceTimersByTime(5000);
    expect(settle).not.toHaveBeenCalled(); expect(f.pending).toBe(false);
  });
  it('a pointer going down while a move waits moves the wait to the release', () => {
    const settle = vi.fn(), f = viewFollower(settle);
    f.moved(); vi.advanceTimersByTime(100); f.down(); vi.advanceTimersByTime(500);
    expect(settle).not.toHaveBeenCalled();
    f.up(); vi.advanceTimersByTime(150); expect(settle).toHaveBeenCalledTimes(1);
  });
});

describe('followPointer', () => {
  it('maps the page pointer to down and up: release, cancel, a move with no button, the window losing focus', () => {
    const target = new EventTarget(), win = new EventTarget();
    const f = { down: vi.fn(), up: vi.fn() };
    followPointer(f, target as unknown as Document, win as unknown as Window);
    const ev = (type: string, o: Record<string, unknown>) => Object.assign(new Event(type), o);
    target.dispatchEvent(ev('pointerdown', { isPrimary: true })); expect(f.down).toHaveBeenCalledTimes(1);
    target.dispatchEvent(ev('pointerdown', { isPrimary: false })); expect(f.down).toHaveBeenCalledTimes(1);   // a second finger
    target.dispatchEvent(ev('pointerup', { isPrimary: true })); expect(f.up).toHaveBeenCalledTimes(1);
    target.dispatchEvent(ev('pointercancel', { isPrimary: true })); expect(f.up).toHaveBeenCalledTimes(2);
    target.dispatchEvent(ev('pointermove', { buttons: 1 })); expect(f.up).toHaveBeenCalledTimes(2);           // still dragging
    target.dispatchEvent(ev('pointermove', { buttons: 0 })); expect(f.up).toHaveBeenCalledTimes(3);
    win.dispatchEvent(new Event('blur')); expect(f.up).toHaveBeenCalledTimes(4);
  });
});
