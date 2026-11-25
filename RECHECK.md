# RECHECK: perbaikan yang menunggu uji ulang

> Ditulis oleh `scripts/recheck_doc.py` dari `verification/records/recheck_ledger.json`. Jangan edit file ini:
> ubah ledger, lalu jalankan `python3 scripts/recheck_doc.py --write` (dicek oleh
> `scripts/tests/test_recheck_doc.py`).

Daftar setiap perbaikan yang belum diuji oleh agen selain pembuatnya, untuk semua eksekusi (AGENTS.md "Findings
and fixes", aturan 8; keputusan user 2026-11-24, EXEC-RECHECK-LIST). Ledger memuat satu baris per temuan, dengan
kunci run + id temuan.

- Uji ulang berjalan hanya dengan persetujuan eksplisit user, setiap kali, dengan model dan tingkat berpikir
  (effort) yang dipilih user. Agen tidak pernah memulainya sendiri.
- Uji ulang yang disetujui mengambil itemnya dari daftar di bawah. Setiap agen menerima temuan asli dari ledger
  (`finding`; untuk baris dari ledger langkah 8: `title` dan `recheck_action`), bukan ringkasan perbaikan.
- Agen mereproduksi kegagalan asli, mencari mekanisme yang sama di tempat lain, dan memeriksa collateral damage:
  tes dari file yang disentuh commit perbaikan, serta halaman dan worker yang memakai file itu.
- Hasilnya (fixed, partly, not fixed, cannot tell) ditulis ke ledger di tugas yang sama, lalu file ini ditulis
  ulang.

## Menunggu uji ulang: 221 item

"Berjalan di" adalah tempat commit perbaikan berjalan (`verification/records/deployed_commits.json`): live, beta,
branch (belum di-deploy), bukan kode (catatan saja), tanpa commit (tidak ada commit yang disebut).

| Area | Eksekusi | Item | live | beta | branch | bukan kode | tanpa commit |
|---|---|---|---|---|---|---|---|
| Akun dan keamanan: re-check ronde 1 (R1) | EXEC-MU-ACCOUNTS | 40 | 36 | 0 | 0 | 4 | 0 |
| Akun dan keamanan: re-check ronde 2 (R2) | EXEC-MU-ACCOUNTS | 38 | 35 | 0 | 0 | 3 | 0 |
| Dua situs dan relay Terminal (cek 3c) | EXEC-MU-ACCOUNTS | 20 | 16 | 0 | 0 | 4 | 0 |
| Situs live: cek sebelum dan sesudah dibuka | EXEC-MU-ACCOUNTS | 21 | 17 | 0 | 0 | 4 | 0 |
| Item lab dan saringan rilis (3f) | EXEC-MU-ACCOUNTS | 16 | 11 | 0 | 0 | 5 | 0 |
| Mode contoh untuk pengunjung dan paket gratis | EXEC-MU-ACCOUNTS | 11 | 11 | 0 | 0 | 0 | 0 |
| Halaman admin dan support (Fase 4) | EXEC-MU-ACCOUNTS | 3 | 3 | 0 | 0 | 0 | 0 |
| Test-out fix round 1 (2026-11-22) | EXEC-MU-ACCOUNTS | 19 | 14 | 0 | 0 | 4 | 1 |
| Perbaikan sesudah ledger langkah 8 (2026-11-22/23) | EXEC-MU-ACCOUNTS | 7 | 3 | 4 | 0 | 0 | 0 |
| Panduan lab, lab dibuka, jendela registrasi (test-out 2026-11-23) | EXEC-MU-ACCOUNTS | 17 | 0 | 13 | 0 | 4 | 0 |
| Tahap preview dan Flow lab (cek langkah 2-3) | EXEC-MU-ACCOUNTS | 20 | 0 | 20 | 0 | 0 | 0 |
| Indikator Pine lab: penutupan ronde 2 (ERRORS M558) | EXEC-PINE-INDICATORS | 3 | 0 | 0 | 3 | 0 | 0 |
| Terminal: ganti timeframe (ERRORS M563) | EXEC-TERMINAL-SESSION-TOGGLE | 1 | 0 | 0 | 1 | 0 | 0 |
| Screener dan Backtest: harga terdistorsi (ERRORS M559-M562) | EXEC-PRICE-DISTORTION | 1 | 0 | 0 | 1 | 0 | 0 |
| Backtest: grid sensitivitas kondisi ya/tidak (ERRORS M558 B-2, UD35) | EXEC-SENSITIVITY-FLAGS | 1 | 0 | 0 | 1 | 0 | 0 |
| Screener: tanda sel Flow dan badge baris saat harga terdistorsi (ERRORS M561, D-1, D-5) | EXEC-PRICE-DISTORTION | 1 | 0 | 0 | 1 | 0 | 0 |
| Terminal: gaya EMA yang tersimpan (ERRORS M564) | EXEC-TERMINAL-SESSION-TOGGLE | 1 | 0 | 0 | 1 | 0 | 0 |
| Terminal: Statistics, Relative performance tanpa data IHSG (ERRORS M565) | EXEC-TERMINAL-SESSION-TOGGLE | 1 | 0 | 0 | 1 | 0 | 0 |

3 item sudah dua ronde diuji ulang. Aturan 8 membolehkan paling banyak dua ronde, lalu sisanya masuk
register keputusan; uji berikutnya hanya dengan keputusan user:

- `wf_c2fe2424-bf4/screener:recheck2/NEW-1`
- `wf_c2fe2424-bf4/terminal:S-6`
- `wf_c2fe2424-bf4/terminal:NEW-1`

### Akun dan keamanan: re-check ronde 1 (R1) (40)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `recheck-r1/R1-1` | Terminal gateway passed terminal-api's own 401/429 straight to the page | `e6dfab52`, `f7a9f49a` | live | M483, M504 | 0 |
| `recheck-r1/R1-3` | EDGE_OWNER could be set to an owner key Orc reserves for the test key | `419ee368` | live | M498 | 0 |
| `recheck-r1/R1-4` | The EDGE gateway's terminal-api account (subscriber 2) expired 2027-10-25 untracked | `e6dfab52` | live | M498 | 0 |
| `recheck-r1/R1-5` | PageFiles' shared caches: a page file counted and audited only for the first owner who reads it | `5d2b8ba4`, `f1242690` | live | - | 0 |
| `recheck-r1/R1-6` | CONTRACT 7's X-Saniti-Capabilities header neither built nor recorded as deferred | `905bad65` | bukan kode | M503 | 0 |
| `recheck-r1/R1-7` | F3: an MFA-passed re-enrolment dropped confirmed_at, so a password-only session could enrol its own authenticator | `419ee368`, `05eaf038` | live | M496 | 0 |
| `recheck-r1/R1-8` | F2: password/reset answered 429 after 20 wrong codes only for an address with an account (enumeration) | `419ee368`, `f7a9f49a`, `c69ca06a`, `33a95315` | live | M507, M517 | 0 |
| `recheck-r1/R1-10` | F1: throttle keys '<prefix>:<value>' shared a scope with caller-typed keys | `419ee368`, `5d563cfa` | live | M494 | 0 |
| `recheck-r1/R1-11` | F4: registering again in the same browser within the hour replaced the registration cookie | `419ee368`, `5d563cfa` | live | M497 | 0 |
| `recheck-r1/R1-12` | F5: USERNAME_TAKEN used none of the code's 5 tries | `419ee368` | live | M494 | 0 |
| `recheck-r1/R1-14` | F7: the sign-in body capped login at 200 characters while registration accepted 254 | `419ee368` | live | M497 | 0 |
| `recheck-r1/R1-15` | F9: the route-walk test accepted a hook route whether or not its handler verifies the signature | `905bad65` | live | M502 | 0 |
| `recheck-r1/R1-17` | The Screener's cached paint showed the last result after the plan lost the Screener | `081c378f`, `5d563cfa` | live | M490, M508 | 0 |
| `recheck-r1/R1-18` | /api/v1/preferences served and stored the tabs' saved items without the tab capability | `081c378f`, `5d563cfa` | live | M489 | 0 |
| `recheck-r1/R1-19` | A drawings refusal (403) was read as 'account unreachable' and the drawing kept in the browser | `5d563cfa`, `135f8051` | live | M532 | 0 |
| `recheck-r1/R1-20` | Browser-class keys named after the added series' tickers survived sign-out and a change of user | `5d563cfa` | live | M490 | 0 |
| `recheck-r1/R1-21` | The two-user acceptance test left out several owned kinds and every cross-owner write by id | `905bad65`, `c3c972e5`, `30fb925c` | live | M534 | 0 |
| `recheck-r1/R1-22` | Values Phase 2 accepts broke the 3c x-terminal-capabilities header | `e6dfab52` | live | M486 | 0 |
| `recheck-r1/R1-23` | Principal.refusal never answered PLAN_EXPIRED for a list or limit restriction | `b16d5728`, `f7a9f49a`, `39e301f2`, `c5674188`, `6b3edc6c`, `8eb45e24` | live | M485 | 0 |
| `recheck-r1/R1-24` | read_grants handed the same RESTRICTIVE list object to every principal with a malformed list | `b16d5728` | live | M486 | 0 |
| `recheck-r1/R1-25` | seed_subscription treated a plan holding '*' = false as the plan that holds every capability | `b16d5728` | live | M486 | 0 |
| `recheck-r1/R1-26` | Two edge-bff 429 answers lacked Retry-After | `e6dfab52` | live | M483 | 0 |
| `recheck-r1/R1-27` | M481 'C3 gaps': the 3a route walks were scoped by module and path | `905bad65` | live | M481, M502 | 0 |
| `recheck-r1/R1-28` | M481 'C3 gaps': the SSE monitor.view re-check had no test | `905bad65` | live | M481, M502 | 0 |
| `recheck-r1/R1-29` | The session's access.limits reported the plan's raw value, not min(plan, HARD) | `b16d5728` | live | M485 | 0 |
| `recheck-r1/R1-30` | D5 second path: preferences served and stored tab content without the tab's capability | `081c378f` | live | M489 | 0 |
| `recheck-r1/R1-31` | 3c design gaps: Terminal limits bind only Terminal paths; PageFiles' owner-free caches conflict | `e6dfab52` | live | M488 | 0 |
| `recheck-r1/R1-32` | No route read screener.preset, so the catalog listed presets the plan does not hold | `5d563cfa`, `33c84c1f` | live | M522 | 0 |
| `recheck-r1/R1-34` | Workers' CAPABILITY_REQUIRED message carried the internal capability key | `5d563cfa` | live | M484 | 0 |
| `recheck-r1/R1-35` | O3b-2 variant: values shown in every result row and /universe stayed gated by id | `05eaf038` | live | M488 | 0 |
| `recheck-r1/R1-36` | Terminal data limits bind only /api/terminal/v1: the workers read everything | `5d563cfa` | live | M488 | 0 |
| `recheck-r1/R1-38` | The Screener boot cache painted an earlier plan's result and catalog after a narrowing | `081c378f` | live | M490 | 0 |
| `recheck-r1/R1-39` | CI never ran the shared session module's tests or the account-page browser tests | `51451d52`, `33c84c1f` | bukan kode | M508, M509, M510, M523 | 0 |
| `recheck-r1/R1-40` | market-ai-orc's conversation-ownership tests were skipped in CI | `51451d52` | bukan kode | M502 | 0 |
| `recheck-r1/R1-41` | Column-level privileges passed every grant guard | `905bad65` | live | M501 | 0 |
| `recheck-r1/R1-42` | admin_audit rewritten by user deletion (FKs ON DELETE SET NULL) | `905bad65` | live | M501 | 0 |
| `recheck-r1/R1-43` | Plan catalog changes left no trace | `905bad65` | live | M501 | 0 |
| `recheck-r1/R1-44` | static/edge-session.js compared with its build by no CI job | `905bad65` | bukan kode | M502 | 0 |
| `recheck-r1/R1-45` | Records contradicted themselves or the decisions (OPEN/not deployed under 'deployed' headings) | `2debe007`, `613c3925`, `c9aef344` | live | M480, M503 | 0 |
| `recheck-r1/R1-46` | Three database backstops no test locked | `905bad65` | live | M502 | 0 |

### Akun dan keamanan: re-check ronde 2 (R2) (38)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `recheck-r2/R2-1` | A switch-on session not past MFA, idle or of a disabled user #1 becomes a full '*' session on the switch-off site | `ccdfb177` | live | M491 | 0 |
| `recheck-r2/R2-2` | Every switch-off start copies EDGE_PASSWORD_VERIFIER over user #1's password | `5d563cfa` | live | M491 | 0 |
| `recheck-r2/R2-3` | Start-up readiness read once: a start during a database outage serves without loops | `ccdfb177`, `f7a9f49a` | live | M492, M505 | 0 |
| `recheck-r2/R2-4` | 3c's entitlement header has no acknowledgement | `e6dfab52`, `f7a9f49a` | live | M486, M504 | 0 |
| `recheck-r2/R2-5` | One unknown dataset id fails every Terminal call of the account with 400 | `e6dfab52` | live | M486 | 0 |
| `recheck-r2/R2-6` | Rollback points listed per service with no order or compatibility floor | `905bad65`, `e2f03de4` | bukan kode | M508 | 0 |
| `recheck-r2/R2-7` | Beta/live on one database: each edge-bff's background loops claim the other site's rows | `5d563cfa`, `e409e753`, `b35607fc`, `f1242690` | live | M505 | 0 |
| `recheck-r2/R2-8` | Beta/live: three per-service secrets key shared rows | `ccdfb177` | live | M491 | 0 |
| `recheck-r2/R2-9` | A password change or sign-in proved before a password reset is still applied after it | `419ee368` | live | M496 | 0 |
| `recheck-r2/R2-10` | A 'password changed' or 'account exists' email holds back the reset code | `419ee368` | live | M494 | 0 |
| `recheck-r2/R2-11` | An MFA code confirms the enrolment another session wrote after the check | `419ee368` | live | M496 | 0 |
| `recheck-r2/R2-12` | MFA tries sent together all pass the consecutive-failure check | `419ee368` | live | M496 | 0 |
| `recheck-r2/R2-13` | Two edge-bff services with different EDGE_MULTIUSER values fight over the shared rows | `5d563cfa` | live | M491 | 0 |
| `recheck-r2/R2-14` | The Monitor shows a refusal's code instead of its words; non-admin sign-in lands on the Monitor | `5d563cfa` | live | M484 | 0 |
| `recheck-r2/R2-15` | Every CAPABILITY_REQUIRED and LIMIT_REACHED carries one fixed sentence per code | `5d563cfa` | live | M484 | 0 |
| `recheck-r2/R2-16` | The shell's own session never follows a change of plan | `5d563cfa` | live | M490 | 0 |
| `recheck-r2/R2-17` | A session that ends under a tab's frame leaves the shell signed in | `5d563cfa` | live | M490 | 0 |
| `recheck-r2/R2-18` | Registration stores names with markup, bidi overrides, control characters and formula prefixes | `5d563cfa` | live | M497 | 0 |
| `recheck-r2/R2-19` | The shell's CSP keeps script-src 'unsafe-inline' and has no form-action | `5d563cfa` | live | M499 | 0 |
| `recheck-r2/R2-20` | No page offers the Phase 1 password change or sign-out everywhere | `081c378f`, `61d9333b` | live | M513 | 0 |
| `recheck-r2/R2-21` | No Strict-Transport-Security on any EDGE answer | `5d563cfa` | live | M499 | 0 |
| `recheck-r2/R2-22` | On the live custom domain sibling hosts are same-site: cookies lack the __Host- prefix | `5d563cfa` | live | M499 | 0 |
| `recheck-r2/R2-23` | Two edge-bff services share every claim loop | `5d563cfa` | live | M491 | 0 |
| `recheck-r2/R2-24` | The hourly purge deletes a never-verified registration but its email_outbox rows stay | `5d563cfa`, `05eaf038` | live | M493 | 0 |
| `recheck-r2/R2-25` | An unexpected exception's text (PostgreSQL DETAIL with email) reaches the logs | `419ee368`, `852d1497` | live | - | 0 |
| `recheck-r2/R2-26` | Per-service settings key shared rows; the email log-mode guard trusts EDGE_ENVIRONMENT=dev | `5d563cfa` | live | M491 | 0 |
| `recheck-r2/R2-29` | Password verifiers use scrypt N=2^14, r=8, p=1, below OWASP's minimum | `419ee368` | live | M495 | 0 |
| `recheck-r2/R2-30` | The Monitor shows plan refusals as internal codes | `5d563cfa` | live | M484 | 0 |
| `recheck-r2/R2-31` | The shell never re-reads its session when X-Edge-Entitlements changes | `5d563cfa` | live | M490 | 0 |
| `recheck-r2/R2-32` | Under Phase 3c the free plan's Terminal draws nothing, not even BBCA | `5d563cfa` | live | M487 | 0 |
| `recheck-r2/R2-33` | A failing hourly cleanup stops every queued AI run | `5d563cfa` | live | M492 | 0 |
| `recheck-r2/R2-34` | No index on the foreign keys to edge_bff.users | `5d563cfa` | live | M493 | 0 |
| `recheck-r2/R2-35` | The email outbox is never purged and its hot reads scan every email | `5d563cfa` | live | M493 | 0 |
| `recheck-r2/R2-36` | A database error at start leaves the AI worker, sender and purges unstarted while /ready says 200 | `ccdfb177`, `2b497f91` | live | - | 0 |
| `recheck-r2/R2-38` | Two edge-bff services act on shared rows with their own switch, configuration and code | `5d563cfa`, `f7a9f49a` | live | M505 | 0 |
| `recheck-r2/R2-39` | Plan saved-item caps answer 422 while the queue cap answers 429 | `5d563cfa` | live | M485 | 0 |
| `recheck-r2/R2-40` | Contract requirements whose code no test holds | `905bad65` | bukan kode | M502 | 0 |
| `recheck-r2/R2-41` | CONTRACT.md still states clauses the code no longer follows or never built | `905bad65`, `e2f03de4` | bukan kode | M503, M508 | 0 |

### Dua situs dan relay Terminal (cek 3c) (20)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `check-3c/wf_02484734-f40/C3-1` | terminal-api refusals before caller identification lose their upstream code (logged as older than 3c) | `1f7ab55c` | live | M504 | 0 |
| `check-3c/wf_02484734-f40/C3-2` | A refused cut download (429/403/401) shows 'A data file could not be downloaded (429)' | `f7a9f49a` | live | M504 | 0 |
| `check-3c/wf_02484734-f40/C3-3` | Live user #1 is sent to terminal-api as a capped owner with the default quota, below the paid plan | `f7a9f49a` | live | M505 | 0 |
| `check-3c/wf_02484734-f40/C3-4` | A capped plan gets a history lock instead of 'no files' for a dataset the ticker lacks | `3eccbbd6` | live | M504 | 0 |
| `check-3c/wf_02484734-f40/C3-7` | A test account whose mark is removed keeps using live in pre-launch; the rule is checked at sign-in only | `f7a9f49a` | live | M506 | 0 |
| `check-3c/wf_02484734-f40/C3-8` | An indicator the plan no longer holds stays drawn when it is restored from storage | `f7a9f49a` | live | M506 | 0 |
| `check-3c/wf_02484734-f40/C3-9` | Refusal words assume an account: a visitor at its quota is told to upgrade, and other refusals say 'still signed in' | `f7a9f49a`, `61d9333b` | live | - | 0 |
| `check-3c/wf_02484734-f40/C3-10` | CONTRACT 4 still marks the pre-launch sign-in rule 'to build' and omits SIGN_IN_CLOSED | `e2f03de4` | bukan kode | M508 | 0 |
| `check-3c/wf_02484734-f40/C3-11` | The two sites' backtest loops share the one-job worker: one site's hand-over replaces the other's job (WORKER_LOST), and a BUSY wait spends the job's deadline | `e409e753` | live | M513 | 0 |
| `check-3c/wf_02484734-f40/C3-12` | User #1 on live gets terminal-api's default quota, shared with its beta usage (duplicate of C3-3) | `f7a9f49a` | live | M505 | 0 |
| `check-3c/wf_02484734-f40/C3-13` | The live mask misses Screener presets: holds_every reads '*' without p.live, so a lab preset is listed on live | `f7a9f49a` | live | M522 | 0 |
| `check-3c/wf_02484734-f40/C3-14` | A failed catalog-names read at start-up leaves Auth.flags empty, so live user #1 sees no tab | `f7a9f49a` | live | M505 | 0 |
| `check-3c/wf_02484734-f40/C3-18` | F3: the operator unlock does not lift a password lock on an account without an MFA enrolment | `f7a9f49a` | live | M507 | 0 |
| `check-3c/wf_02484734-f40/C3-19` | F4: a sign-in at a registration's 3-mails-a-day cap moves the registration to a cookie no browser holds | `f7a9f49a` | live | M507 | 0 |
| `check-3c/wf_02484734-f40/C3-20` | F5: a wrong current password in the password change is not counted toward the 100-failure cap | `f7a9f49a` | live | M507 | 0 |
| `check-3c/wf_02484734-f40/C3-21` | F6: the password change's limit answers with the sign-in's sentence | `f7a9f49a` | live | M507 | 0 |
| `check-3c/wf_02484734-f40/C3-23` | The only test of R1-17 ('a refused plan drops the cached result') runs in no CI workflow | `e2f03de4` | bukan kode | M508 | 0 |
| `check-3c/wf_02484734-f40/C3-24` | The rollback block of 20261119_050 does not run as written | `e2f03de4`, `7ca79186`, `1c3bbe4a` | bukan kode | M508 | 0 |
| `check-3c/wf_02484734-f40/C3-26` | The live admin's Terminal is held to default quotas on the beta admin's owner row (duplicate of C3-3) | `f7a9f49a` | live | M505 | 0 |
| `check-3c/wf_02484734-f40/C3-27` | No Phase 3c deploy-steps record (order, sha256 values, changelog entries, params) | `0ec5e5ab` | bukan kode | M508 | 0 |

### Situs live: cek sebelum dan sesudah dibuka (21)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `live-site/wf_b98c2b6c-166/accounts:A1` | User #1 signs in on live only under the reserved-name substitute login, has no email and no reset way back | `0909a70c`, `2b497f91` | live | M513 | 0 |
| `live-site/wf_b98c2b6c-166/site:S2` | Sign out everywhere and the password change on live do not end user #1's beta '*' sessions | `61d9333b` | live | - | 0 |
| `live-site/wf_b98c2b6c-166/site:S3` | The admin's live login is not the beta's login, and user #1 has no email (duplicate of accounts:A1) | `0909a70c`, `2b497f91` | live | M513 | 0 |
| `live-site/wf_b98c2b6c-166/switchon:S2` | No rollback was written for the first live deployment; removing edge-bff-live strands its backtest jobs | `d810d88b` | bukan kode | - | 0 |
| `live-site/wf_b98c2b6c-166/switchon:S3` | edge-bff-live references are chains, and the M308 tool finds only direct consumers | `d810d88b` | live | M308, M515 | 0 |
| `live-site/wf_b98c2b6c-166/switchon:S5` | User #1's live login and missing email are not in Option A (duplicate of accounts:A1) | `0909a70c`, `2b497f91` | live | - | 0 |
| `live-site/wf_0799ce99-16e/accounts:ACC-1` | Replacing a phone: after the fresh code the /mfa page goes to the workspace and never shows the new set-up | `dcb87955` | live | M515 | 0 |
| `live-site/wf_0799ce99-16e/accounts:ACC-2` | With the recovery codes locked, the MFA page hides the authenticator path, which still works | `dcb87955`, `0293f97c`, `937853a2` | live | M519 | 0 |
| `live-site/wf_0799ce99-16e/accounts:ACC-3` | Phone and recovery codes both lost: the live admin has no way back | `dcb87955` | bukan kode | M515 | 0 |
| `live-site/wf_0799ce99-16e/accounts:ACC-5` | Pre-launch: a non-test account's right password counts as a failure, and the 11th try shows the rate limit | `d810d88b` | live | - | 0 |
| `live-site/wf_0799ce99-16e/accounts:ACC-6` | The live web process holds the admin's plaintext first password and address | `6db6cf2e` | live | - | 0 |
| `live-site/wf_0799ce99-16e/visitor:F1` | A visitor's Terminal shows locked datasets as empty data (Rp 0, no broker data, 0 events, no 1H, no 730-day note) | `741c0b6f`, `a5eb7a27` | live | M515, M518 | 0 |
| `live-site/wf_0799ce99-16e/visitor:F4` | The Privacy and Terms links on every public page lead nowhere | `6db6cf2e` | live | - | 0 |
| `live-site/wf_0799ce99-16e/visitor:F5` | The Terminal shows developer notes to every visitor | `6db6cf2e` | live | M515 | 0 |
| `live-site/wf_0799ce99-16e/shared:SH1` | The site that holds the shared backtest-worker slot takes it again before the other can; one site's queue holds back the other's jobs | `b35607fc`, `f1242690` | live | - | 0 |
| `live-site/wf_0799ce99-16e/shared:SH2` | Two live variables read backtest-worker through edge-bff, and the consumer script misses the second step | `d810d88b` | live | - | 0 |
| `live-site/wf_0799ce99-16e/ops:F3` | Railway labels every edge-bff log line 'error' | `d810d88b` | live | - | 0 |
| `live-site/wf_0799ce99-16e/ops:F5` | EXEC option A's rollback as written: no service named, not durable, a domain removal, the job not prepared | `d810d88b` | bukan kode | - | 0 |
| `live-site/wf_0799ce99-16e/ops:F7` | Two live references are still chains (duplicate of shared:SH2) | `d810d88b` | live | - | 0 |
| `live-site/wf_0799ce99-16e/ops:F9` | Some records lag the running site (M512, M500, M513 A1, PROJECT_CONTEXT) | `d810d88b` | bukan kode | M500, M512, M513 | 0 |
| `live-site/wf_0799ce99-16e/ops:F10` | The admin's first password is in the live site's process environment (duplicate of ACC-6) | `6db6cf2e` | live | - | 0 |

### Item lab dan saringan rilis (3f) (16)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `3f/SERVE-2` | Lab build files readable from the browser cache after sign-out | `55ce548c`, `c5674188` | live | M523 | 0 |
| `3f/SERVE-7` | 'The second factor passed' never applies on the deployed beta (records) | `33c84c1f` | bukan kode | M523 | 0 |
| `3f/L2` | Screener worker refusals list and describe every registry item before the plan gate | `37297b74`, `f1242690` | live | M523 | 0 |
| `3f/L5` | Until 3f reaches live, a lab item on main reaches live principals via shared workers | `ec1bd29c`, `4b35b5ed`, `27e33943`, `af1dc9f4` | live | - | 0 |
| `3f/L8` | Code-defined items are outside the release filter | `48c8d522`, `f1242690` | live | - | 0 |
| `3f/CAT-1` | A catalog entry's release kind is the first kind listing its id; nothing refuses a repeat | `33c84c1f` | live | - | 0 |
| `3f/CAT-3` | Worker INVALID_CONDITION 'allowed' lists every id of a kind | `37297b74`, `f1242690` | live | - | 0 |
| `3f/CAT-5` | Lab item names stay in Screener catalog text outside the lists | `55ce548c`, `f1242690` | live | M523 | 0 |
| `3f/B4` | Screener page unfiltered; four REGISTRIES entries dead; lists branch fails open | `33c84c1f`, `9723caf7`, `c9aef344` | bukan kode | M523 | 0 |
| `3f/B7` | Backtest legacy Flow cards (fnet, broker, top5) are release items the filter cannot cover | `48c8d522`, `f1242690` | live | - | 0 |
| `3f/W2` | restrict's raw walk overflows the stack on deep nesting | `9723caf7`, `f1242690` | live | M524 | 0 |
| `3f/W3` | Records: engine-version attribution and the after-normalize wording stale | `9723caf7`, `f1242690` | bukan kode | - | 0 |
| `3f/BUN2-7` | B4 recorded FIXED while two of three parts unchanged | `9723caf7`, `c9aef344` | bukan kode | M523 | 0 |
| `3f/CS-5` | A lab transform metric hidden but its presets stay and the worker never gates it | `9723caf7` | live | - | 0 |
| `3f/TRC2-8` | Guards' messages and AGENTS tell agents to add items/tabs as lab | `9723caf7`, `f1242690` | bukan kode | - | 0 |
| `3f/CRIT-3` | Items written in code are more than LIVE_PROMOTION names | `48c8d522`, `f1242690` | live | - | 0 |

### Mode contoh untuk pengunjung dan paket gratis (11)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `example-mode/wf_33a88511-3e1/guest-exposure-2` | Watchlist '30 October' LQ45 list inferred from membership first recorded 9-10 November | `fe0097e7`, `a30815c1`, `1c972f22` | live | M527 | 0 |
| `example-mode/wf_33a88511-3e1/capture-publisher-1` | Watchlist example takes LQ45 members recorded 10 Nov as the members of 30 Oct | `fe0097e7`, `a30815c1` | live | - | 0 |
| `example-mode/wf_33a88511-3e1/pages-shell-screener-stored-layout` | Screener example reads the visitor's stored panes/column order/pop sizes/extra columns at import | `fe0097e7`, `59b54a06`, `c9aef344` | live | M527 | 0 |
| `example-mode/wf_33a88511-3e1/pages-shell-overview-banner-stale` | Shell caches each example index for the page's life; Overview banner keeps an old date | `fe0097e7` | live | M527 | 0 |
| `example-mode/wf_33a88511-3e1/tests-ci-1` | Browser tests do not check that the view-only layer stops the page's own handlers | `fe0097e7` | live | M527 | 0 |
| `example-mode/wf_33a88511-3e1/tests-ci-3` | New Backtest example browser test (slow variant) failed once in CI, green only through the M510 rerun | `fe0097e7`, `59b54a06` | live | M510 | 0 |
| `example-mode/wf_33a88511-3e1/tests-ci-6` | The admin case claimed for the example routes is not tested | `fe0097e7` | live | M527 | 0 |
| `example-mode/wf_33a88511-3e1/records-promotion-1` | Watchlist example's 'LQ45 members on 30 October' are those first recorded 10 Nov; rule never checked | `fe0097e7`, `a30815c1` | live | - | 0 |
| `example-mode/wf_33a88511-3e1/records-promotion-2` | Example-mode smoke skips the Overview and the Watchlist; no automated smoke probes the example routes | `fe0097e7`, `59b54a06`, `a30815c1`, `4b35b5ed` | live | - | 0 |
| `example-mode/wf_ce647f0d-9a8/guest-exposure-2` | Radar example stores its whole board (near misses, every level and gate, 35 Feature 07 measures) | `59b54a06`, `c9aef344` | live | M527 | 0 |
| `example-mode/wf_ce647f0d-9a8/view-layer-shell-storage-order-test-misses-reexport` | test_example_storage does not see an export...from placed before the storage import | `59b54a06`, `c9aef344` | live | M527 | 0 |

### Halaman admin dan support (Fase 4) (3)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `phase4/wf_9a01b336-48e/page-tests-records-2` | A sign-in that passes the authenticator step loses the page it was shown at | `180d8952`, `6b3edc6c` | live | M541, M546 | 0 |
| `phase4/wf_9a01b336-48e/deploy-3` | TELEGRAM_NOTIFY_URL validation accepts the empty-port value this project was hit by | `180d8952`, `c5674188`, `8eb45e24` | live | M536 | 0 |
| `phase4/wf_9a01b336-48e/page-tests-records-6` | CONTRACT 10's account list names usage counters the built list does not return | `180d8952`, `c5674188`, `8eb45e24` | live | M536 | 0 |

### Test-out fix round 1 (2026-11-22) (19)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `wf_c72ae04c-a73/round:R1-23` | An ended plan is told CAPABILITY_REQUIRED instead of PLAN_EXPIRED on Terminal limit refusals (the quota-0 path in capabilities_header) | `39e301f2`, `c5674188`, `8eb45e24` | live | M485 | 0 |
| `wf_c72ae04c-a73/phase4:page-tests-records-2` | Its locking admin-page test is flaky: the frame's /backtest-app/ answers 404 (now M546, same root cause as M541) | `c5674188`, `6b3edc6c`, `8eb45e24` | live | M541, M546 | 0 |
| `wf_c72ae04c-a73/phase4:deploy-3` | TELEGRAM_NOTIFY_URL validation accepted no port, port 0, port above 65535 and host '-' | `c5674188`, `8eb45e24` | live | M536 | 0 |
| `wf_c72ae04c-a73/phase4:page-tests-records-6` | The admin Accounts list received the usage counters but did not draw them | `c5674188` | live | - | 0 |
| `wf_c72ae04c-a73/round:SH1` | The shared Backtest slot taken back by the site that just gave it (no test that the loop passes a nonzero window) | `b35607fc`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/round:R1-5` | Page files counted for the first reader only (A1: each distinct file once per reader per hour); the If-None-Match 304 path had no test | `5d2b8ba4`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/round:L2-CAT-3` | Worker refusals name items outside allow (an unreadable or missing id leaks the registry lists) | `37297b74`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/round:CRIT-3` | Items the built-ins compute by key (I10, I29) could be set to lab | `48c8d522`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/3f:W2` | A deep request overflows the stack: 500 instead of 422 (Backtest refKinds, Screener core validate) | `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/3f:W3` | Records: CONTRACT 1248-1261's engine-version attribution and run.ts:201's wording were stale after M521 and TR-2 | `f1242690` | bukan kode | M521 | 0 |
| `wf_c72ae04c-a73/round:SERVE-3` | A lab tab named in the public shell files; PUBLIC_SHELL not derived (edge-boot.js omitted) | `f9853cd5`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/round:CRIT-1` | The Terminal restore drops a saved indicator its build lacks: no browser round-trip test, and a throw during restore loses drawn entries | `7ba76c39`, `c5674188` | live | - | 0 |
| `wf_c72ae04c-a73/round:SERVE-2/SERVE-4/CAT-5` | Lab files left in the browser cache after sign-out-all; CAT-5 did not scan screener-registry.json; L11 probe file | `55ce548c`, `c5674188`, `f1242690` | live | - | 0 |
| `wf_c72ae04c-a73/round:RULE-9` | Record statuses edited by hand and left stale after deploys | `d33aeb35`, `c9aef344` | bukan kode | M289, M311, M417, M506, M520, M541 | 0 |
| `wf_c72ae04c-a73/3f:BUN2-7` | B4 recorded FIXED while its dead-spec part was unwritten | `c9aef344` | bukan kode | M523 | 0 |
| `wf_c72ae04c-a73/3f:TRC2-8` | The guards' messages still said a new item or tab starts as lab | `f1242690` | bukan kode | - | 0 |
| `wf_c72ae04c-a73/example-mode:wf_ce647f0d-9a8/guest-exposure-2` | The Radar example stores the whole board: a future publisher field reaches visitors (fail-open trim) | `c9aef344` | live | - | 0 |
| `wf_c72ae04c-a73/example-mode:wf_ce647f0d-9a8/view-layer-shell-storage-order-test-misses-reexport` | The storage-order test missed a comment-prefixed import placed before the storage module | `c9aef344` | live | - | 0 |
| `wf_c72ae04c-a73/deploy-compat` | The live site's older edge-bff (4b35b5ed) against the HEAD workers once they deploy from main | - | tanpa commit | - | 0 |

### Perbaikan sesudah ledger langkah 8 (2026-11-22/23) (7)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `after-ledger/M539` | CI "too many clients": the store fixture leaked a pool per test | `4f1e6d3e` | live | M539 | 0 |
| `after-ledger/M546` | The admin-page browser test counted /backtest-app/ 404 (built_pages fixture) | `6b3edc6c` | live | M541, M546 | 0 |
| `after-ledger/M547` | The AI page's Sources fold closed again when the panel was drawn anew | `4f1e6d3e` | live | M547 | 0 |
| `after-ledger/M548` | The lab item guard lifted; the look-ahead gate passed a lab indicator without computing it | `6ab63c15` | beta | M548 | 0 |
| `after-ledger/step7` | The payment shell (adapters, order state machine, hook routes off unless EDGE_PAYMENTS_PROVIDER, migration 20261123_001) | `d6f5b18a` | beta | - | 0 |
| `after-ledger/M550` | The preview release stage (admin only on the live site) | `1894adfc` | beta | M550 | 0 |
| `after-ledger/M551` | The lab Flow indicator's registration point and its dry-run fixes D1-D6 | `521c5048`, `f1436829`, `b24361fd` | beta | M551 | 0 |

### Panduan lab, lab dibuka, jendela registrasi (test-out 2026-11-23) (17)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `wf_4181198a-09f/GC-1` | the guide said the beta and the screener-worker wait for CI (off since 2026-11-23) | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F1` | the look-ahead gate passed a lab indicator whose formula throws on every call (`safely`) | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F2` | a lab candle pattern was opened without a dry run and would turn the gate red: candle patterns are held (`LAB_KIND_HELD`), with a carried part. | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F3` | the released-text guard read only `name`; it reads `label` and `short` too (`tests/test_releases.py` `NAME_FIELDS`, a self-test per field | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F4` | the Backtest worker checked a stop line against the full registry before the plan's allow, so a lab id answered INVALID_LINE and an unknown one UNKNOWN_INDICATOR; the allow is checked first (`src/vali | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F5` | `http_smoke.py` reads `LAB_PROBE` from `shared/release-filter.mjs`; the filter's comment names the .svg. | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/LLA-F6` | the CRIT-1 browser test's docstring. | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/GC-2` | stale "no lab item" texts (LIVE_PROMOTION section 3, FUTURE_PLAN, a test docstring). | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/GC-3` | the Backtest tripwire was red against `main`: its worker baseline recorded under EXEC-MU-ACCOUNTS with the user's words (`scripts/screener/backtest_worker_baseline.json`; the tripwire OK) | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/GC-4` | the guide cites symbols, not line numbers | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/GC-5` | the guide cites symbols, not line numbers | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/GC-6` | the guide cites symbols, not line numbers | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/F6` | the window's other paths are tests (`apps/edge-bff/tests/test_step9_window_paths.py`, P1-P9; P1 and P7 hold today's residuals for UD7 and UD22). | `083dbc23` | beta | M549 | 0 |
| `wf_4181198a-09f/F1` | the step-9 plan did not name UD7's exposure while the window is open, nor the watch on the live logs | `083dbc23` | bukan kode | M549 | 0 |
| `wf_4181198a-09f/F2` | the step-9 plan did not name the close's confirmation and its exact value | `083dbc23` | bukan kode | M549 | 0 |
| `wf_4181198a-09f/F4` | the step-9 plan held the residuals as facts, not as open questions to the user | `083dbc23` | bukan kode | M549 | 0 |
| `wf_4181198a-09f/F7` | the step-9 plan's line citations | `083dbc23` | bukan kode | M549 | 0 |

### Tahap preview dan Flow lab (cek langkah 2-3) (20)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `wf_6a8c44c8-978/P1` | No test covers the one line that keeps a preview indicator out of the live Terminal menu (indMenu.ts:120) | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/P2` | Count and contiguity pins fail as soon as a Flow indicator goes preview or released, and the guide does not name them | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/P3` | Two comments say the lab build marks lab entries with `release`; only preview entries are marked | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/P4` | The coverage guard does not see an item named by value (`{"indicator": "I55"}`); latent, because screener-overlay.json is not in a public bundle | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-1` | No indicator or Flow indicator can be put at preview: the shipped-code guard counts preview as lab, and Part C puts the formula exactly where that guard looks | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-2` | A family value {"all": true} makes a paid account hold every preview item on the live site; the database and the reader accept it, and the only guard reads the migrations' seeded plans | `bb638e12` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-3` | The stored examples' preset line (examples.py:333) has no test: reading it as lab-only passes every suite, and a preview preset then withholds the whole Screener example | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-4` | The 'never preview either' rules have self-tests that plant lab only | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-5` | Stored examples match bare ids across kinds: a preset at preview (or lab) withholds examples that name the released metric of the same id | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/PV-6` | INDICATOR_BETA_TO_LIVE.md Notes contradicts itself on Flow indicators and overstates preview | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F1` | Guide step 1 tells the agent to edit a generated file (FLOW_INDICATORS_SPEC.xlsx) instead of its source, build_spec_workbook.py | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F2` | Nothing checks a lab Flow formula's values, and the new 'has a formula' gate passes an all-null formula | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F3` | The Flow look-ahead gate never varies numeric parameters, so a leak that appears only at a non-default window passes | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F4` | Step 8 (release) names one test, but a released Flow indicator breaks three page tests; the guide never says which FL id to take | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F5` | Part C (preview) cannot pass two edge-bff tests: they treat every stage other than released as lab | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F6` | flowKit hands lab code the memoized cohort arrays; a lab formula that changes one changes a released output that another principal is served | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F7` | A lab Flow indicator turns the Backtest tripwire red, and neither the Flow section nor Part A has the step that records it | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F8` | Stale records still say a Flow indicator cannot be lab | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F9` | Guide step 1 and Part A step 9 are ambiguous or wrong for Flow: family naming, generator vocabulary, expected version changes | `61fb22c4` | beta | M552 | 0 |
| `wf_6a8c44c8-978/F10` | A lab item named in shipped code is refused by the guard's self-test, whose message does not name the fix | `61fb22c4` | beta | M552 | 0 |

### Indikator Pine lab: penutupan ronde 2 (ERRORS M558) (3)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `wf_c2fe2424-bf4/screener:recheck2/NEW-1` | Both look-ahead gates test in_categories with every category chosen, so a read of a later bar passes | `c91e2809`, `2f8b012c` | branch | M558 | 3 |
| `wf_c2fe2424-bf4/terminal:S-6` | The two colour boxes do not share the colours in use on the chart (indicators' and compare lines') | `c91e2809`, `8530a75e` | branch | M558 | 3 |
| `wf_c2fe2424-bf4/terminal:NEW-1` | Label boxes snap y with the canvas's horizontal pixel ratio, so their top and bottom fall off the grid | `c91e2809`, `8530a75e` | branch | M558 | 3 |

### Terminal: ganti timeframe (ERRORS M563) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M563` | A timeframe switch reloaded the whole Terminal page | `cb688250`, `8530a75e` | branch | M563 | 1 |

### Screener dan Backtest: harga terdistorsi (ERRORS M559-M562) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M559-M562` | Price distortion detected by a date rule, read wrong for three stocks, and hidden instead of marked | `4799ee94`, `e9fc3ab6`, `db7bf27e`, `af806747`, `6b86cf6e`, `fa1f1f60`, `6a2473fd`, `6d254189` | branch | M559, M560, M561, M562 | 1 |

### Backtest: grid sensitivitas kondisi ya/tidak (ERRORS M558 B-2, UD35) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M558-B-2` | The sensitivity grid moved a fixed 0.5 threshold on a yes/no condition | `185c0dd5`, `ff6228c1` | branch | M558 | 1 |

### Screener: tanda sel Flow dan badge baris saat harga terdistorsi (ERRORS M561, D-1, D-5) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M561-D5` | Flow cells were never marked across a corporate action or a price break; old price breaks kept a row badge forever | `61def35d`, `6d254189` | branch | M561 | 1 |

### Terminal: gaya EMA yang tersimpan (ERRORS M564) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M564` | The Terminal's EMA lost its saved colour, width and offset on every load and every timeframe switch | `ab64b8cf` | branch | M564 | 0 |

### Terminal: Statistics, Relative performance tanpa data IHSG (ERRORS M565) (1)

| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |
|---|---|---|---|---|---|
| `errors/M565` | Statistics wrote NaN into its SVG lines when IHSG has no close on the chart | `ab64b8cf` | branch | M565 | 0 |

## Hitungan per status

| Status | Arti | Jumlah |
|---|---|---|
| `waiting` | sudah diperbaiki, menunggu uji ulang oleh agen selain pembuatnya | 221 |
| `fixed` | diuji ulang agen lain: beres | 115 |
| `partly` | diuji ulang agen lain: sebagian beres, sisanya belum diperbaiki | 0 |
| `not_fixed` | diuji ulang agen lain: belum beres | 0 |
| `cannot_tell` | diuji ulang agen lain: tidak bisa dipastikan | 0 |
| `open` | belum diperbaiki | 90 |
| `accepted` | diterima user apa adanya | 4 |
| `obsolete` | tidak berlaku lagi | 5 |
| **Total** | | **435** |

Dari 90 baris `open`, 25 punya baris pemilik di PLAN.md atau EXEC.md dan 65 belum
(aturan 1: setiap bagian yang terbuka butuh pemilik dan pemicu).
