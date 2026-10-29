/* Structured logs: one JSON object per line on stdout ({ts, level, event, ...fields}), from the HTTP thread and the
   compute threads alike (a thread hands its lines to the main thread, thread.ts). Callers pass only fields that are not
   secret: never a header, a request body, a key or a presigned URL (report 6.16). The same shape as the backtest
   worker's log.ts, which the image does not carry. */
export type Level = 'info' | 'warn' | 'error';

let sink = (line: string): void => { process.stdout.write(line + '\n') };
/** Where the lines go: stdout, or (threads) the main thread, or (tests) a collector. */
export function setLogSink(f: (line: string) => void): void { sink = f }
export const writeLine = (line: string): void => sink(line);

export function log(level: Level, event: string, fields: Record<string, unknown> = {}): void {
  let line: string;
  try { line = JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields }) }
  catch { line = JSON.stringify({ ts: new Date().toISOString(), level, event, unloggable: true }) }
  sink(line);
}

/** The part of an error that may be logged: its name, code and message, and for an unexpected error the first stack
    frames (function, file and line only). The core and terminal.ts never put a key or a URL into a message. */
export function errorFields(e: unknown, withStack = false): Record<string, unknown> {
  const x = e as { name?: string; code?: unknown; message?: string; stack?: string } | null;
  const out: Record<string, unknown> = { error: x?.name ?? typeof e, code: typeof x?.code === 'string' ? x.code : null, message: typeof x?.message === 'string' ? x.message : String(e) };
  if (withStack && typeof x?.stack === 'string') out.stack = x.stack.split('\n').slice(1, 6).map(s => s.trim());
  return out;
}

/** The replica that wrote a line (report 6.16 run log `replica`; Railway sets RAILWAY_REPLICA_ID), else the host. */
export const REPLICA = (process.env.RAILWAY_REPLICA_ID || process.env.HOSTNAME || 'local').slice(0, 64);
