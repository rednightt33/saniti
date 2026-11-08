/* The fake terminal-api of the flow cost benchmark in a process of its own (its 1.5 M broker rows stay out of the
   measured worker's heap): prints "URL <url> ROWS <rows per day>" and serves until killed. */
import { startFakeTerminal } from '../fake-terminal.mjs';
import { BROKER, CLASSES, DAYS, U0 } from './market.ts';

const fake = await startFakeTerminal({ key: 'p'.repeat(40), publication: { finished_at: '2026-10-27T10:00:00Z', ...U0, actions: [], broker: BROKER, brokers: CLASSES } });
console.log(`URL ${fake.url} ROWS ${BROKER[DAYS[0]].length}`);
setInterval(() => {}, 1e6);
