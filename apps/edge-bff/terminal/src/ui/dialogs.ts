/* EXEC-IND-PRESETS: small dialogs above every other window (a name, a confirmation) and a message line, in the saved
   layouts' look (.lay-* in terminal.css). Escape closes them wherever the focus is, Tab stays inside, and the focus goes
   back to what opened them. */
const esc = (t: string) => t.replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);

function modal(inner: string, label: string, onClose: () => void) {
  const back = document.createElement('div'); back.className = 'lay-back top';
  back.innerHTML = `<div class="lay-dlg" role="dialog" aria-modal="true" aria-label="${esc(label)}">${inner}</div>`;
  document.body.appendChild(back);
  const opener = document.activeElement as HTMLElement | null, dlg = back.firstElementChild as HTMLElement;
  const key = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return }
    if (e.key !== 'Tab') return;
    const f = [...dlg.querySelectorAll<HTMLElement>('button:not([disabled]),input')].filter(x => x.offsetParent !== null);
    if (!f.length) return;
    const i = f.indexOf(document.activeElement as HTMLElement);
    if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus() } else if (!e.shiftKey && (i === f.length - 1 || i < 0)) { e.preventDefault(); f[0].focus() }
  };
  const close = () => { document.removeEventListener('keydown', key, true); back.remove(); onClose(); if (opener?.isConnected) opener.focus?.() };
  document.addEventListener('keydown', key, true);
  back.addEventListener('pointerdown', e => { if (e.target === back) close() });
  return { dlg, close };
}

/** a name sent through `commit` (its refusal shows under the field); resolves to the name, or null when cancelled */
export function askName(title: string, suggest: string, commit: (name: string) => Promise<void>, ok = 'Save') {
  return new Promise<string | null>(resolve => {
    let result: string | null = null;
    const { dlg, close } = modal(`<h3>${esc(title)}</h3><input class="lay-in" type="text" maxlength="120" value="${esc(suggest)}" aria-label="Name">
      <div class="lay-err" role="alert"></div><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1" data-ok>${esc(ok)}</button></div>`, title, () => resolve(result));
    const input = dlg.querySelector('input') as HTMLInputElement, err = dlg.querySelector('.lay-err') as HTMLElement, btn = dlg.querySelector('[data-ok]') as HTMLButtonElement;
    const go = async () => {
      const n = input.value.replace(/\s+/g, ' ').trim();
      if (!n) { err.textContent = 'Give it a name.'; input.focus(); return }
      btn.disabled = true; err.textContent = '';
      try { await commit(n); result = n; close() } catch (e: any) { err.textContent = e?.message || 'Not saved. Try again in a minute.'; btn.disabled = false; input.focus() }
    };
    btn.onclick = go; (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
    input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go() } });
    input.focus(); input.select();
  });
}

export function confirmBox(text: string, yes: string, danger = true) {
  return new Promise<boolean>(resolve => {
    let result = false;
    const { dlg, close } = modal(`<p>${esc(text)}</p><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1${danger ? ' warn' : ''}" data-ok>${esc(yes)}</button></div>`, 'Confirm', () => resolve(result));
    (dlg.querySelector('[data-ok]') as HTMLElement).onclick = () => { result = true; close() };
    (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
    (dlg.querySelector('[data-x]') as HTMLElement).focus();
  });
}

/** one message line at the bottom of the window; a failure stays until it is closed */
let toastEl: HTMLElement | null = null, timer: any = 0;
export function say(text: string, error = false) {
  if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'lay-toast top'; toastEl.setAttribute('role', 'status'); toastEl.setAttribute('aria-live', 'polite');
    toastEl.addEventListener('click', e => { if ((e.target as HTMLElement).closest('.lay-tx')) toastEl!.classList.remove('show') }); document.body.appendChild(toastEl) }
  toastEl.innerHTML = `<span>${esc(text)}</span>${error ? '<button type="button" class="lay-tx" aria-label="Close message">×</button>' : ''}`;
  toastEl.classList.toggle('err', error); toastEl.classList.add('show'); clearTimeout(timer);
  if (!error) timer = setTimeout(() => toastEl!.classList.remove('show'), 2600);
}
