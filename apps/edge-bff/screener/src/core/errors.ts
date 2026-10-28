/* The one error class of the screener core (EXEC-SCREENER; report API CONTRACT 8.8). Every refusal names the field
   where there is one and says how to fix it (AGENTS.md "Gates and evidence" (d)); its code is one of contract.ts
   ErrorCode (or the worker-only DATA_VERSION_PENDING), so the worker answers it as it is: status
   WORKER_ERROR_STATUS[code], body {"error": {code, field, message, details}}. The backtest core's ValidationError codes never travel: registry.ts mapCoreError translates them.
   Pure module (no DOM, no Node API): the page may import it to read an error body the same way. */
import { WORKER_ERROR_STATUS } from './contract.ts';
import type { ApiError, WorkerErrorCode } from './contract.ts';

/** code: one of report 8.8's 20 codes, or the worker-only DATA_VERSION_PENDING (409; report 8.8 note, 6d.4 rule 3),
    which only the worker raises and edge-bff turns into 503 SCREENER_NOT_READY, so it never reaches the page. */
export class ScreenerError extends Error {
  readonly code: WorkerErrorCode;
  readonly field?: string;
  readonly details?: Record<string, unknown>;
  constructor(code: WorkerErrorCode, message: string, field?: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ScreenerError'; this.code = code; this.field = field; this.details = details;
  }
  /** HTTP status of the code (report 8.8; WORKER_ERROR_STATUS = ERROR_STATUS plus DATA_VERSION_PENDING 409). */
  get status(): number { return WORKER_ERROR_STATUS[this.code] }
  /** The wire body; fields that are not set are left out. */
  toApi(): ApiError {
    return { error: { code: this.code, message: this.message, ...(this.field !== undefined ? { field: this.field } : {}), ...(this.details !== undefined ? { details: this.details } : {}) } };
  }
}

export const isScreenerError = (e: unknown): e is ScreenerError => e instanceof ScreenerError;
