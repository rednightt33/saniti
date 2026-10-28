/* The one interface through which the Screener page reaches its data (report FRONTEND INTEGRATION 9.1, PAGE LOAD
   SEQUENCE 6c). Production: live.ts (edge-bff /api/v1/screener/*, session and CSRF as the Backtest page). Tests:
   tests/fixture (the prototype's synthetic data, for the visual check only) and tests/smoke (a stub whose answers
   arrive late, ERRORS M253). The page modules never compute an indicator, a condition or a match themselves: they
   render what this interface returns (report I1). */
import type {
  CatalogResponse, CountsRequest, CountsResponse, Definition, ItemKind, ItemsResponse, PreviewRequest, PreviewResponse,
  PutItemRequest, RunRequest, RunResponse, SavedItem, UniverseResponse, ValidateResponse, WatchlistResponse,
} from '../core/contract.ts';

/** GET /api/v1/auth/session: who is signed in (the boot pointer is per login, 6c.3) and the CSRF token of the writes. */
export interface Session { login: string; csrf: string }

/** A conditional GET (report 6c.5 item 5): 200 with the body and its bytes, or 304 when `If-None-Match` named the
    current bytes. etag: the sha256 of the JSON bytes that edge-bff announces, unquoted; null when it sent none. */
export type Conditional<T> =
  | { status: 200; etag: string | null; body: T; bytes: Uint8Array }
  | { status: 304; etag: string | null };

/** A run answer with its bytes, so the page can keep the last open screen's result in the browser cache (6c.3). */
export interface RunAnswer { body: RunResponse; bytes: Uint8Array }

/** An answer that is an error, as the page shows it: the refusal's code, field and message (report 8.8), the HTTP
    status, Retry-After in seconds where the server sent one, and the error's details. */
export class ApiFailure extends Error {
  constructor(message: string, readonly code = '', readonly status = 0, readonly field?: string,
              readonly retryAfter: number | null = null, readonly details: Record<string, unknown> | null = null) { super(message) }
}
/** Whether a call failed because its caller aborted it (a newer edit replaced it): nothing to show. */
export const isAbort = (e: unknown) => (e as { name?: string } | null)?.name === 'AbortError';

export interface CallOpts { signal?: AbortSignal }

export interface ScreenerApi {
  /** 'live', 'fixture' or 'smoke': the fixture keeps the prototype's sample-data words (texts.ts sourceNote). */
  kind: 'live' | 'fixture' | 'smoke';
  session(): Promise<Session>;
  /** GET catalog and GET universe with If-None-Match (6c.4 S2). */
  catalog(ifNoneMatch?: string | null): Promise<Conditional<CatalogResponse>>;
  universe(ifNoneMatch?: string | null): Promise<Conditional<UniverseResponse>>;
  /** POST run / preview: `signal` aborts the call (latest wins, 6c.4 S8); the call then rejects with an AbortError. */
  run(req: Omit<RunRequest, 'client_order'>, opts?: CallOpts): Promise<RunAnswer>;
  preview(req: Omit<PreviewRequest, 'client_order'>, opts?: CallOpts): Promise<PreviewResponse>;
  validate(definition: Definition): Promise<ValidateResponse>;
  counts(req: CountsRequest): Promise<CountsResponse>;
  items(kind: ItemKind): Promise<ItemsResponse>;
  putItem(itemId: string, req: PutItemRequest): Promise<SavedItem>;
  deleteItem(itemId: string): Promise<void>;
  watchlist(): Promise<WatchlistResponse>;
  /** PUT (on) or DELETE (off) watchlist/{ticker}; both idempotent. */
  watch(ticker: string, on: boolean): Promise<void>;
}
