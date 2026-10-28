/* Errors of the worker in the contract's shape {error: {code, field?, message?, details?}} (report API CONTRACT 8.8,
   8.11): the core's ScreenerError at its WORKER_ERROR_STATUS (refusals 422, DATA_VERSION_* and BUSY 409, TIMEOUT 504,
   DATA_* 424, SCREENER_NOT_READY 503); the backtest core's DataError of a refresh as 424 DATA_UNAVAILABLE or
   DATA_INTEGRITY (no snapshot can serve); the worker's own protocol answers (401 UNAUTHORIZED, 404 NOT_FOUND, 405
   METHOD_NOT_ALLOWED: never reached by edge-bff's routes, the backtest worker's codes) as HttpError. Anything
   unexpected is 500 INTERNAL_ERROR without its message (it is logged, not answered). */
import type { ApiError, WorkerErrorCode } from '../../edge-bff/screener/src/core/contract.ts';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';

export type ErrorBody = ApiError['error'];

/** A protocol answer outside the contract's codes (the key, a route, a method), with its status. */
export class HttpError extends Error {
  status: number; code: string; headers: Record<string, string>;
  constructor(status: number, code: string, message?: string, headers: Record<string, string> = {}) {
    super(message ?? code); this.name = 'HttpError'; this.status = status; this.code = code; this.headers = headers;
  }
}

/** A contract refusal raised by the worker itself (the core's class, so the shape and status are the core's). */
export const refuse = (code: WorkerErrorCode, message: string, field?: string, details?: Record<string, unknown>) => new ScreenerError(code, message, field, details);

const body = (code: string, field?: string, message?: string, details?: Record<string, unknown>): ErrorBody =>
  ({ code, ...(field ? { field } : {}), ...(message ? { message } : {}), ...(details ? { details } : {}) });

/** The status, body and extra headers of an error; `known` false = an unexpected error (the caller logs it). */
export function toApiError(e: unknown): { status: number; error: ErrorBody; headers: Record<string, string>; known: boolean } {
  if (e instanceof ScreenerError) return { status: e.status, error: e.toApi().error, headers: retryHeaders(e), known: true };
  if (e instanceof HttpError) return { status: e.status, error: body(e.code, undefined, e.message === e.code ? undefined : e.message), headers: e.headers, known: true };
  if (e instanceof DataError) {
    const code = e.code === 'DATA_INTEGRITY' ? 'DATA_INTEGRITY' : 'DATA_UNAVAILABLE';
    return { status: 424, error: body(code, e.field, e.message, e.details), headers: {}, known: true };
  }
  return { status: 500, error: body('INTERNAL_ERROR', undefined, 'The worker failed; the error is in its log.'), headers: {}, known: false };
}

/** Retry-After of a SCREENER_NOT_READY (details.retry_after_seconds), as edge-bff reads it (screener.py seconds_of). */
function retryHeaders(e: ScreenerError): Record<string, string> {
  const s = e.details?.retry_after_seconds;
  return e.code === 'SCREENER_NOT_READY' && typeof s === 'number' && Number.isFinite(s) ? { 'retry-after': String(Math.max(1, Math.round(s))) } : {};
}

/** An error crossing a thread boundary loses its class: the plain answer goes instead. */
export interface SerialError { status: number; error: ErrorBody; known: boolean; cancelled: boolean }
export const serialError = (e: unknown, cancelled = false): SerialError => {
  const a = toApiError(e);
  return { status: a.status, error: a.error, known: a.known, cancelled };
};
/** The thread's answer rebuilt on the main thread, as the error it was (a ScreenerError keeps its code and details). */
export function fromSerial(s: SerialError): Error {
  if (s.status === 500 || !s.known) return Object.assign(new Error(s.error.message ?? 'INTERNAL_ERROR'), { serial: s });
  return new ScreenerError(s.error.code as WorkerErrorCode, s.error.message ?? s.error.code, s.error.field, s.error.details);
}
