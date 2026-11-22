# Midtrans for QRIS and Virtual Account: research before the payment shell (2026-11-22)

The user, 2026-11-22: "Untuk kerangka pembayaran, rencananya kita akan pakai Mitrans. Dengan pembayaran QRIS atau
virtual account. ... sepertinya Mitrans itu menggunakan sistem seperti webhook. Jadi ketika sudah bayar, maka akan ada
webhook yang mengirimkan user ID yang sudah membayar. Feel free to do research before membuat kerangka pembayaran."

Read from Midtrans' official pages on 2026-11-22 (sources at the end). UNCONFIRMED marks what no official page said.
Nothing here is built; the payment shell (EXEC.md option A, item 6) starts on the user's go.

## 1. Integration

- **Snap** (Midtrans' hosted payment page): `POST https://app[.sandbox].midtrans.com/snap/v1/transactions`, Basic auth
  with base64(ServerKey + ":"); answers 201 `{token, redirect_url}`. Either redirect the person to `redirect_url` or
  open snap.js (`app[.sandbox].midtrans.com/snap/snap.js`, `data-client-key`) as a popup [S1].
- `order_id`: at most 50 characters, letters, digits and `- _ ~ .`, used once [S1] (a FAQ says a new token for the same
  id revokes the old one [S15]: use a new id per attempt).
- `enabled_payments` [S3]: QRIS `other_qris` (needs GoPay or ShopeePay QRIS active on the account [S4]); VA `bca_va`,
  `bni_va`, `bri_va`, `echannel` (Mandiri Bill), `permata_va`, `cimb_va`, `danamon_va`, `bsi_va`, `seabank_va`,
  `saqu_va`, `other_va`. One method listed: Snap skips its picker [S2].
- **Core API** (`/v2/charge`, own UI) needs a separate production activation [S5]; not needed for the shell.
- **Expiry:** VA and a Snap token 24 h by default [S2][S5]; Snap `other_qris` 15 minutes by default (20 s to 7 days)
  [S4]; `expiry{start_time, unit, duration}` in Snap [S2].

## 2. The notification (webhook)

- Set once per environment (Sandbox, Production) in the dashboard, Settings > Configuration, "Payment Notification URL";
  per transaction `X-Append-Notification` / `X-Override-Notification` (up to 3 URLs) [S11]. Public HTTPS URL, standard
  port, no auth, no custom headers; Midtrans speaks TLS up to 1.2 [S11].
- Fields: `order_id`, `transaction_id`, `transaction_status`, `status_code`, `gross_amount` (a string, "10000.00"),
  `payment_type`, `fraud_status`, `currency`, `signature_key`, `settlement_time`, method fields; `custom_field1-3` (255
  characters each) come back [S2][S9][S11].
- **It carries no user id of ours.** A payment is linked to the person through our own `order_id` (a row we wrote when
  the order was made); `custom_field1-3` can repeat the plan as a cross-check.
- Statuses: `pending` (waiting), `settlement` (paid), `capture` (card only), `deny`, `cancel`, `expire`, `failure`,
  `refund`, `partial_refund`; success = `settlement` (with `fraud_status` `accept` when present) [S11][S12].
- Verify: `signature_key == SHA512(order_id + status_code + gross_amount + ServerKey)` [S11]; then confirm with
  `GET /v2/{order_id}/status` (the official clients do) [S13][S16].
- Retries: none after 2xx; 500 once, 503 four times, 400/404 twice, others 5 times at about 2, 10, 30, 90, 210 minutes;
  15 s timeout, answer within 5 s [S11].
- Duplicates and out of order are possible (a `settlement` before its `pending`): handle idempotently, never move a
  settled order back [S11].
- Midtrans publishes its notification source IPs [S14] but recommends the signature check as the guard.

## 3. Renewal

- The Subscription API covers only card and GoPay [S17]. **QRIS and VA cannot renew automatically:** every period is a
  new payment the person makes (a new order), so EDGE reminds before the end and may keep a grace period.

## 4. The return page

- The finish/unfinish/error redirect gets `?order_id&status_code&transaction_status` "to display custom message"; the
  notification decides [S2][S16]. The return page only shows; it never activates a plan.

## 5. Cost and money

- VA Rp 4,000 per transaction, QRIS 0.7%, no setup or monthly fee; "Gaming & digital product companies are subject to
  different rates" (confirm EDGE's rate with Midtrans); VAT wording differs between the English and Indonesian page
  [S18]. Withdrawal Rp 5,000 [S18]; funds can be withdrawn 3 business days after settlement [S19][S20].

## 6. Going live

- Sandbox at once; Production after activation [S23].
- Documents: an individual KTP and NPWP; a PT/CV its deed, the Kemenkumham decree, the director's KTP and NPWP, the
  company NPWP, NIB [S21].
- Website: live, reachable, matching the business, clear product information and prices in IDR [S22]. Terms, refund
  policy or contact as a stated requirement: UNCONFIRMED (EDGE hides its Privacy and Terms links until their texts
  exist: to settle before applying). Activation time for QRIS/VA: UNCONFIRMED.

## 7. Refunds

- QRIS (GoPay/ShopeePay acquirer): full or partial by dashboard or `POST /v2/{id}/refund/online/direct`, within 45
  days for GoPay [S25][S27]. VA: no refund through Midtrans; the merchant returns the money itself [S25][S26].

## 8. What this means for EDGE (inferred, to decide with the user)

- One `payment_orders` row per attempt: our `order_id` (opaque, new per attempt), the account, the plan, the period,
  the expected amount in IDR, its expiry; `payment_events` keep every notification (unique per order and status).
- The webhook route already designed (CONTRACT 6 and 11: `POST /api/v1/hooks/payments/{provider}`, signature over the
  raw body) verifies, confirms with Get Status, checks the amount and currency against the order, then activates or
  extends the subscription in one transaction (the `subscriptions` table, provider `midtrans` added), answers 2xx fast.
- Snap by redirect (no change to the site's Content Security Policy); the popup needs `*.midtrans.com` and others
  allowed [S2].
- The Server Key lives only in a Railway variable the user enters; the Client Key is needed only for the popup.
- Sandbox webhook to the beta, Production webhook to the live site (the database is shared, so one order is applied
  once whichever site receives it).

## Sources

- S1 https://docs.midtrans.com/docs/snap-snap-integration-guide
- S2 https://docs.midtrans.com/docs/snap-advanced-feature
- S3 https://docs.midtrans.com/reference/request-body-json-parameter
- S4 https://docs.midtrans.com/reference/other-qris
- S5 https://docs.midtrans.com/docs/coreapi-core-api-bank-transfer-integration
- S9 https://docs.midtrans.com/docs/coreapi-advanced-features
- S11 https://docs.midtrans.com/docs/https-notification-webhooks
- S12 https://docs.midtrans.com/reference/transaction-status
- S13 https://docs.midtrans.com/reference/get-transaction-status
- S14 https://docs.midtrans.com/docs/ip-address
- S15 https://docs.midtrans.com/docs/technical-faq
- S16 https://github.com/Midtrans/midtrans-nodejs-client, https://github.com/Midtrans/midtrans-python-client
- S17 https://docs.midtrans.com/reference/create-subscription
- S18 https://midtrans.com/pricing
- S19 https://docs.midtrans.com/docs/when-can-i-withdraw-my-transaction-funds-from-midtrans
- S20 https://docs.midtrans.com/docs/balance-page-manage-withdraw-your-funds
- S21 https://docs.midtrans.com/docs/what-are-the-legal-documents-required-for-midtrans-account-registration
- S22 https://docs.midtrans.com/docs/what-are-the-website-or-application-criterias-for-registering-a-midtrans-account
- S23 https://midtrans.com/passport
- S25 https://docs.midtrans.com/docs/what-payment-method-that-have-refund-feature
- S26 https://docs.midtrans.com/docs/how-can-i-refund-transaction
- S27 https://docs.midtrans.com/reference/direct-refund-transaction
