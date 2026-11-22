/* Phase 4, the admin page: the answers of /api/v1/admin/* (app/admin.py; its docstring lists every route). Times are ISO
   strings as edge-bff sends them; an address and a phone come masked unless revealed. */

export interface StepState { needed: boolean; enrolled: boolean; available: boolean }

export interface Overview {
  accounts: { by_status: Record<string, number>; active_by_plan: Record<string, number>; test_accounts: number };
  sessions_live: number;
  support: { new: number; done: number; unsent: number; images_bytes: number };
  emails: { waiting: number; failed_7d: number };
  site: string; commit: string; support_storage_mb: number;
}

export interface Account {
  user_id: number; username: string; first_name: string | null; last_name: string | null;
  email: string | null; phone: string | null; role: string; status: string; test_account: boolean;
  plan: string | null; plan_ends: string | null; created_at: string; last_sign_in_at: string | null;
}
export interface Accounts { users: Account[]; next: number | null }

export interface AuditRow {
  audit_id: number; at: string; action: string; actor_user_id: number | null; actor: string | null;
  target_user_id?: number | null; target?: string | null; before: unknown; after: unknown; reason: string | null;
}
export interface AuditPage { audit: AuditRow[]; next: number | null }

export interface AccountDetail {
  account: Account; email_verified_at: string | null; mfa: 'confirmed' | 'pending' | 'none';
  subscriptions: { subscription_id: number; plan_key: string; status: string; starts_at: string; expires_at: string | null;
                   provider: string | null; created_at: string }[];
  overrides: { capability_key: string; value: unknown; reason: string | null; expires_at: string | null; created_at: string }[];
  sessions: { live: number; last_seen: string | null };
  usage: Record<string, number>;
  audit: AuditRow[];
}

export interface Plans {
  plans: { plan_key: string; display_name: string; is_default: boolean; for_guests: boolean }[];
  capabilities: { capability_key: string; kind: string; unit: string | null; display_name: string; means: string | null;
                  value_min: number | null; value_max: number | null; item_pattern: string | null }[];
  values: { plan_key: string; capability_key: string; value: unknown; version: number; updated_at: string }[];
}

export interface Settings { settings: Record<string, unknown>; telegram_summary: boolean }

export interface TicketRow {
  ticket_id: number; created_at: string; site: string; kind: string; kind_label: string; subject: string; images: number;
  status: 'new' | 'done'; done_at: string | null; telegram_sent_at: string | null; images_purged_at: string | null;
  username: string; plan: string | null;
}
export interface Tickets { tickets: TicketRow[]; next: number | null }

export interface Ticket {
  ticket_id: number; created_at: string; site: string; kind: string; kind_label: string; subject: string; body: string;
  details: Record<string, unknown>; status: 'new' | 'done'; done_at: string | null; done_by: string | null; images: number;
  images_purged_at: string | null; images_due: string | null;
  files: { position: number; filename: string; content_type: string; bytes: number }[];
  telegram_sent_at: string | null; telegram_attempts: number;
  sender: { user_id: number; username: string; email: string | null };
}

/** the page's only data path (src/api.ts live; tests/fixture/main.ts an in-memory one for the look check) */
export interface AdminApi {
  stepState(): Promise<StepState>;
  stepUp(code: string): Promise<void>;
  overview(): Promise<Overview>;
  users(q: Record<string, string>): Promise<Accounts>;
  user(id: number): Promise<AccountDetail>;
  reveal(id: number, field: 'email' | 'phone', reason: string): Promise<{ field: string; value: string | null }>;
  audit(q: Record<string, string>): Promise<AuditPage>;
  auditFile(q: Record<string, string>): Promise<Blob>;
  plans(): Promise<Plans>;
  settings(): Promise<Settings>;
  tickets(q: Record<string, string>): Promise<Tickets>;
  ticket(id: number): Promise<Ticket>;
  imageUrl(id: number, position: number): string;
  setStatus(id: number, status: 'done' | 'new'): Promise<Ticket>;
  telegram(id: number): Promise<{ sent: boolean }>;
  deleteTicket(id: number, reason: string): Promise<void>;
}
