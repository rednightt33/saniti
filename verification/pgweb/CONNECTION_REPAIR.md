# Pgweb connection repair — 2026-10-13

User authorized repair: "Ok jalankan langkah perbaikan".

The public pgweb service in lucid-patience/dev was running but its database connection was
closed. PostgreSQL logged password authentication failures for manually submitted `pgweb`
credentials at 09:51–09:59 WIB. Those failures did not prove the stored URL was stale.

A temporary private Function, `pgweb-credential-ops` (`1847b74e-0ac4-4dcf-86fe-a6816d5624c4`),
tested the existing server-side `pgweb.PGWEB_DATABASE_URL` reference. Deployment
`8fd58483-66cf-4957-a0bd-9830152e57c8` reached SUCCESS and the stored credential logged in
successfully. No password reset was needed.

The existing URL was then submitted to pgweb's `/api/connect`. Read-only query verification
at 10:52 WIB returned role `pgweb`, database `railway`,
`default_transaction_read_only=on`, and zero writable public tables. The role has no
superuser, role creation, database creation, replication, or RLS bypass privileges; it is a
member of `pgweb_reader`. A bounded SELECT from Feature04 also succeeded.

No database row, schema, role grant, password, or permanent service variable changed.
The temporary Function has no cron, domain, or volume, and restart policy NEVER. The first cleanup request was cancelled; after the user asked what it did and authorized
"Ok jalankan", project-wide deletion succeeded. Inventory confirmed the service absent
and no detached volume.

For reconnection, paste the complete PGWEB_DATABASE_URL into the Scheme tab. In Standard
mode use only its decoded password component in Password. PGWEB_AUTH_USER/PGWEB_AUTH_PASS
authenticate the web page and are separate from PostgreSQL credentials. No secret value is
recorded here.
