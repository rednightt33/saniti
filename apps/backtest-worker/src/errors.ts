/* Errors of the worker in the contract's shape {error: {code, field?, message?, details?}} with the HTTP statuses of
   CONTRACT.md section 11: validation 422, market data 424 (DATA_MISSING, DATA_INTEGRITY, DATA_UNAVAILABLE), the job
   protocol 401 / 404 / 409, a synchronous call over its time 504 TIMEOUT. A job's error is the same object in
   JobStatus.error. Anything unexpected is INTERNAL_ERROR without its message (it is logged, not answered). */
import type { ApiError } from '../../edge-bff/backtest/src/core/contract.ts';
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';
import { Cancelled, EngineDataError } from '../../edge-bff/backtest/src/core/engine.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';

export type ErrorBody = ApiError['error'];

/** An error the worker raises itself, with its status. */
export class WorkerError extends Error {
  status: number; code: string; field?: string; details?: Record<string, unknown>;
  constructor(status: number, code: string, message?: string, field?: string, details?: Record<string, unknown>) {
    super(message ?? code); this.name = 'WorkerError'; this.status = status; this.code = code; this.field = field; this.details = details;
  }
}
/** A request the page's controls cannot produce (422). */
export const invalid = (code: string, field: string, message: string, details?: Record<string, unknown>) => new WorkerError(422, code, message, field, details);

const body = (code: string, field?: string, message?: string, details?: Record<string, unknown>): ErrorBody =>
  ({ code, ...(field ? { field } : {}), ...(message ? { message } : {}), ...(details ? { details } : {}) });

/** The status and body of an error; `known` false = an unexpected error (the caller logs it). */
export function toApiError(e: unknown): { status: number; error: ErrorBody; known: boolean } {
  if (e instanceof WorkerError) return { status: e.status, error: body(e.code, e.field, e.message, e.details), known: true };
  if (e instanceof ValidationError) return { status: 422, error: body(e.code, e.field, e.message), known: true };
  if (e instanceof DataError) return { status: 424, error: body(e.code, e.field, e.message, e.details), known: true };
  if (e instanceof EngineDataError) return { status: 424, error: body(e.code, e.field, e.message), known: true };
  if (e instanceof Cancelled) return { status: 409, error: body('CANCELLED'), known: true };
  return { status: 500, error: body('INTERNAL_ERROR', undefined, 'The worker failed; the error is in its log.'), known: false };
}

/** An error crossing a thread boundary loses its class: the plain {status, error, known} goes instead. */
export interface SerialError { status: number; error: ErrorBody; known: boolean; cancelled: boolean }
export const serialError = (e: unknown): SerialError => ({ ...toApiError(e), cancelled: e instanceof Cancelled });
