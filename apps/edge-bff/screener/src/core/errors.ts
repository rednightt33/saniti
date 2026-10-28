/* The one error class of the screener core (EXEC-SCREENER; report API CONTRACT 8.8). Every refusal names the field
   where there is one and says how to fix it (AGENTS.md "Gates and evidence" (d)); its code is one of contract.ts
   ErrorCode, so the worker answers it as it is: status ERROR_STATUS[code], body {"error": {code, field, message,
   details}}. The backtest core's ValidationError codes never travel: registry.ts mapCoreError translates them.
   Pure module (no DOM, no Node API): the page may import it to read an error body the same way. */
import { ERROR_STATUS } from './contract.ts';
import type { ApiError, ErrorCode } from './contract.ts';

export class ScreenerError extends Error {
  readonly code: ErrorCode;
  readonly field?: string;
  readonly details?: Record<string, unknown>;
  constructor(code: ErrorCode, message: string, field?: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ScreenerError'; this.code = code; this.field = field; this.details = details;
  }
  /** HTTP status of the code (report 8.8). */
  get status(): number { return ERROR_STATUS[this.code] }
  /** The wire body; fields that are not set are left out. */
  toApi(): ApiError {
    return { error: { code: this.code, message: this.message, ...(this.field !== undefined ? { field: this.field } : {}), ...(this.details !== undefined ? { details: this.details } : {}) } };
  }
}

export const isScreenerError = (e: unknown): e is ScreenerError => e instanceof ScreenerError;
