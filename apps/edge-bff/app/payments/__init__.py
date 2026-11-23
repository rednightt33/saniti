"""EDGE multi-user, step 7: the payment shell (EXEC.md EXEC-MU-ACCOUNTS option A item 6; CONTRACT.md sections 6 and 11;
FINDINGS.md "Payments (plug-in later)"). The user, 2026-11-22: "langkah 7 berkaitan dengan pembuatan kerangka
pembayaran, harap disiapkan saja infrastrukturnya. Untuk tesnya nanti kita buat fase tersendiri karena akun Mitrans
belum siap."

- `adapters`: the Adapter interface (create_checkout, verify_webhook, fetch_status) and its providers: `manual` (the
  admin activates a plan; no notification), `test` (HMAC-signed fake notifications and a provider record for the
  tests), `midtrans` (its offline parts: the notification's signature, its status words, the amount, the order number;
  Snap and Get Status raise PaymentNotConfigured until the Midtrans phase: no call leaves EDGE).
- `orders`: payment_orders and payment_events (migration 20261123_001), the state machine that applies a verified event
  to its order and the subscription in one transaction, and the reconciliation of pending orders.
- `routes`: POST /api/v1/hooks/payments/<provider>, off unless EDGE_PAYMENTS_PROVIDER names that provider.
"""
