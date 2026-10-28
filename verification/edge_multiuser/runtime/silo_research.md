# Silo research: one service copy per user, or a shared pool (EDGE Screener, Backtest, Terminal)

Question (user, 2026-10-28): "jika screener, backtest, dan terminal adalah idle, dalam artian ketika user tidak mengakses
maka tidak ada biaya, we might as well to create more the same service. Jadi misalkan ada service, kita duplicate service
yang sama untuk serve user ID 123, kemudian kita duplicate lagi service yang sama untuk serve user 456 dan seterusnya.
Coba saja di explore pakai benchmark yang best practice." Priorities: cost, speed (users must not wait long), accuracy.
AI Orc is out of scope.

Scope: research only. No repository change, no Railway mutation, no database write. Railway was only read
(`railway status --json`, CLI 5.71.0). The only other contact was timed `GET /health` calls to the public health route of
`telegram-trigger`. That route only answers `{"status":"ok"}` (`apps/telegram-trigger/telegram_trigger.py:544-548`).
Web pages were read on 2026-10-28. Labels: FACT (with a source), INFERENCE, PROPOSED, UNKNOWN. Quotes are exact unless
marked "paraphrase". A FACT from a Railway community thread (station.railway.com) is staff-stated or user-quoted, not
official documentation, and says so.

---

## 0. Answer in short

1. **The premise is only half true on Railway today.** FACT: none of the EDGE services sleeps. Only `telegram-trigger`
   and `telegram-monitor` have `sleepApplication: true` (`.railway/railway.ts:113, 147`). The EDGE services still cost
   little while idle, because Railway bills resident memory. Measured cost: terminal-api USD 1.52 a month, edge-bff 1.00,
   backtest-worker 0.51 (`verification/edge_multiuser/capacity_fairness_scale_cost.md` §2.2). The new screener-worker is
   different. Its idle cost is the price snapshot it keeps in memory: about 0.4-0.7 GB, or USD 4-7 a month for each copy
   (06d.4, INFERENCE).
2. **Railway can make a service cost no compute while idle (Serverless, formerly App Sleeping), with conditions.**
   - The service sleeps only after 5-10 minutes without *outbound* packets.
   - The first request after sleep pays a cold boot and "may return a 502".
   - Sleep applies to all replicas of the service.
   - A service that polls, or holds a database connection, never sleeps.
   - The docs list "latency-sensitive first requests" and workers that "poll queues" as bad fits (§2.1).
   - Measured here (§2.10, n = 1): a small Python service fell asleep about 5-6.5 minutes after its last request.
     Waking it cost about 1 s (HTTP 200 in 1.27 s, against 0.24-0.30 s warm).
3. **A copy per user (the AWS "silo" model, or "automated single-tenant deployments") fits these services badly.**
   (INFERENCE, §4.)
   - All three serve the same public market data to every user. Each copy would repeat the same download, decode and
     precompute: 15-25 s to `/ready`, 0.4-0.7 GB, for the Screener.
   - A user returning after more than about 10 minutes would wait that long again.
   - The copies stop being cheaper as soon as users are active at the same time: IDX market hours concentrate them.
   - Railway caps a project at 100 services. Error text: "Your plan only allows 100 services in a single project"
     (§2.7). The project already has 28. So at most 24 users fit, at 3 services per user.
   - A new account may create only 25 services per day (staff, §2.7).
   - Every push would redeploy N copies.
4. **Best practice for this profile is a pool, or a "bridge" with silos reserved for exceptions.** (FACT from AWS and
   Azure guidance, §3.)
   - **Pool:** shared, stateless workers that hold the publication once. Logical isolation through owner keys,
     per-owner lanes, quotas and fair queues.
   - **Bridge exceptions:** a silo only for a tenant with a compliance or premium requirement, or for untrusted code.
     The AI sandbox is such a case, but it is out of scope here.
   - AWS: silo "trades economies of scale and operational efficiency for compliance, business, or domain
     considerations".
   - Azure: per-customer resources are "likely unsustainable" at scale.
   - Fly.io's per-user machine guidance targets isolated dev environments and "user-generated (or LLM-generated) code".
5. **The user's goal, no cost while nobody uses the service, can be met without copies.** (PROPOSED, §5.)
   - Enable Serverless on the *pooled* service, once its idle outbound traffic is removed.
   - Pre-warm it from a cron before market open. Then one cold start serves everyone, instead of one cold start per user
     and session.
   - Keep the per-user fairness that 6d and the capacity report already designed: owner lanes, round-robin claim and
     per-owner quotas.
   - Measure first with the benchmarks in §6.

---

## 1. The premise checked against the live system

| Claim | Finding | Label and evidence |
|---|---|---|
| "When nobody uses Screener, Backtest or Terminal there is no cost" | None of the EDGE services sleeps. `sleepApplication: true` exists only on `telegram-trigger` and `telegram-monitor`. EDGE services run 24/7 and are billed for resident memory and used CPU. | FACT `.railway/railway.ts:106-113, 140-147, 158-190`; `railway status --json` 2026-10-28 19:37 UTC: `telegram-monitor` `SLEEPING`, every EDGE service `SUCCESS` |
| What they cost while mostly idle | 30-day estimates from 2026-10-24..28: terminal-api avg 0.142 GB, USD 1.52/month; edge-bff 0.082 GB, 1.00; backtest-worker 0.049 GB, 0.51 | FACT `verification/edge_multiuser/capacity_fairness_scale_cost.md` §2.2 (usage API, scaled ×7.5) |
| Screener-worker idle cost | Holds the bars and 53 default indicators in memory: about 0.4-0.7 GB steady, so about USD 4-7/month per copy, idle or busy | INFERENCE 06d.4 from FACT components (`audit/benchmark.md` §2, §2d) |
| Where per-user cost already sits | Each EDGE user's own rows are small and in Postgres, keyed by `owner_key`. The Terminal page computes in the user's browser and downloads straight from the bucket, whose egress is free. | FACT 06d §6d.1 table (`store.py:59-65`, `backtest.py:516-526`); bucket egress `verification/terminal_api/PHASE1_PHASE2.md:271-272` |
| Market data differs per user? | No. The Screener snapshot is a pure function of (publication, engine). Only the screen definition differs between users. | FACT/PROPOSED 06d.2, 06d.4 |

INFERENCE: the idle-cost saving that copies could bring is at most the idle floor of the pool:
- about USD 1-2 a month per service for terminal-api, backtest-worker and edge-bff;
- about USD 6-12 a month for a 1-2 replica Screener.

Copies multiply that floor per user unless every copy really sleeps.

---

## 2. Railway, from the official documentation (read 2026-10-28)

### 2.1 Serverless (App Sleeping)

| Topic | Exact text | URL |
|---|---|---|
| Trigger | "When Serverless is enabled for a service, Railway automatically detects inactivity based on outbound traffic." "Inactivity is based on the detection of any outbound packets" | https://docs.railway.com/reference/app-sleeping |
| Window | "Once a service stops sending packets it is considered inactive after 5 minutes." "...so in practice a service sleeps somewhere between 5 and 10 minutes after its last outbound traffic." | same |
| Window (conflicting docs) | "If your service sends no outbound packets for 10 minutes, it is considered inactive and goes to sleep." / "After 10 minutes, a serverless container that has not done any work will be fully put to sleep" | https://docs.railway.com/guides/cut-idle-costs-serverless ; https://docs.railway.com/guides/scaling-your-application |
| Inbound vs outbound | "Inbound requests are not measured directly, but anything your service sends in response to them is" | app-sleeping |
| What keeps it awake | Paraphrase: database connection poolers, framework telemetry, requests to other services over the public or private network. "Any of these resets the 10-minute timer, so a worker that holds a persistent Postgres connection" … Private traffic "still counts as outbound and still prevents sleep." | https://docs.railway.com/deployments/serverless ; cut-idle-costs guide |
| Wake | "A service is woken when it receives traffic from the internet or from another service in the same project" "The first request made to a slept service wakes it." | app-sleeping |
| Cold start | "It may take a small amount of time for the service to spin up again on the first request" ("cold boot time"). No number is published. | app-sleeping |
| First request | "The first request sent to a slept service may return a 502 Bad Gateway response." | app-sleeping |
| Replicas | "Enabling Serverless will apply the setting across all Replicas" (no "keep N warm" option) | app-sleeping |
| Activation | "Serverless is applied to a container when that container is created." "Enabling it on a running service does not affect the container already running" | app-sleeping |
| Priority | "Slept services still consume a slot on Railway's infrastructure." "Slept services are de-prioritized on Railway's infrastructure." "In rare cases a wake requires a rebuild." | serverless page; cut-idle-costs guide |
| Billing while asleep | "Railway bills by usage: RAM at $10 per GB per month and CPU at $20 per vCPU per month, metered by the minute." A slept service "accrues no compute charges." "Egress is billed separately at $0.05 per GB either way; Serverless only affects compute charges." | cut-idle-costs guide |
| Bad fits | Paraphrase of the guide's "Bad fits" list: latency-sensitive first requests; workers that hold database connections or poll queues; long-lived websockets; databases. | cut-idle-costs guide |
| Cron instead | "For scheduled work, cron jobs are usually a better model than a sleeping service." Cron: UTC, minimum interval 5 minutes (paraphrase) | cut-idle-costs guide |
| Static IP | "Services with Static Outbound IPs enabled may remain awake even when idle." | app-sleeping |

INFERENCE:
- "Compute" in the billing sentence covers both RAM and CPU, since the sentence before it names both. So a sleeping
  service is billed for neither.
- Volumes are not mentioned. Volume storage is billed per GB-month regardless (§2.2).
- The docs do not say whether a woken container keeps its ephemeral disk. UNKNOWN (U3).

### 2.2 Pricing (https://docs.railway.com/reference/pricing/plans, https://docs.railway.com/reference/pricing)

| Item | Exact text |
|---|---|
| RAM (containers) | "$10 / GB / month ($0.000231 / GB / minute)" |
| CPU (containers) | "$20 / vCPU / month ($0.000463 / vCPU / minute)" |
| Egress | "$0.05 / GB ($0.000000047683716 / KB)" |
| Volume | "$0.15 / GB / month ($0.000003472222222 / GB / minute)" |
| Plans | Free "$0 / month"; Hobby "$5 / month"; Pro "$20 / month"; Enterprise "Custom". "the Pro plan includes $20 of resource usage per month." |
| Principle | "You are only charged for the resources you actually use" |
| Private network | "No egress costs: Internal traffic doesn't count toward egress billing" (https://docs.railway.com/networking/private-networking/how-it-works) |
| VMs and Sandboxes (new product) | RAM "$50 / GB / month" ("$0.001157 / GB / minute"), CPU "$50 / vCPU / month", egress "$0.05 / GB"; "VM usage is metered per second". Memory is 5× and CPU 2.5× the container rate. |

Cross-check: the same container rates are recorded in 06d (`06d_multi_user_scale_cost.md:32-35`, read the same day).
FACT, they agree.

### 2.3 Plan limits

| Item | Value | Source |
|---|---|---|
| Per-service maxima | "Depending on the plan you are on, you are allowed to use up these resources per service." "Note that these are maximum values and include replica multiplication." Pro: 42 replicas, 1 TB RAM, 1,000 vCPU, 100 GB ephemeral, 1 TB volume. Hobby: 6 replicas, 48 GB, 48 vCPU. | reference/pricing/plans |
| Per-replica size seen | 24 vCPU / 24 GB per replica (Postgres 4 GB) | FACT `railway metrics`, capacity report §2 item 5; `RAILWAY_CHANGELOG.md:791-793` |
| Total replicas | "Railway supports a maximum of 50 total replicas across all regions." | https://docs.railway.com/guides/autoscale-horizontally |
| Plan of this project | Pro | FACT `railway status --json` deployment `meta.plan = "pro"` (capacity report §2 item 5, re-read 2026-10-28) |
| Services per project | Not in the docs. Error text quoted by a Pro user on 2026-06-05: "Too many services in project. Your plan only allows 100 services in a single project." Railway staff (2026-05-26) call it the Pro plan's "100 services per project limit". | https://station.railway.com/questions/increase-project-service-limit-from-100-80621cdd ; https://station.railway.com/questions/25-services-per-day-19e355a8 |
| Service creation rate | Not in the docs. Error text: "You've hit the service creation limit for new accounts (25 services per day)." Staff (2026-05-26): a rolling 24-hour window, "account-level, not project-level"; it "cannot be raised, even temporarily". | 25-services-per-day thread |
| Volumes per project | User-quoted error "You can only have 10 volumes per project" (plan not stated; moderator: upgrade to Pro to request an increase) | https://station.railway.com/questions/i-m-developing-a-multi-tenanting-applica-7200c926 |
| Concurrent builds, build timeout | Not stated in the pages read | UNKNOWN (U6) |
| Services in this project today | 28 services, 27 instances in `dev` | FACT `railway status --json` 2026-10-28 |

### 2.4 Replicas, load balancing, autoscaling, healthchecks

| Topic | Exact text | URL |
|---|---|---|
| Manual replicas | "Scale horizontally by manually increasing the number of replicas for a service in the service settings." | https://docs.railway.com/reference/scaling |
| Public traffic | "Railway will randomly distribute public traffic to the replicas of that region." Multi-region: "automatically route public traffic to the nearest region and then randomly distribute requests to the replicas within that region." | reference/scaling; https://docs.railway.com/deployments/scaling |
| Stickiness | "For now Railway does not support sticky sessions nor report the usage of the replicas within the metrics view." | reference/scaling |
| Vertical | "By default Railway will scale your service up to the specified vCPU and Memory limits of your plan." | reference/scaling |
| Horizontal autoscaling | None built in: "the replica count is a setting you control, and by default it stays where you set it." The guide builds an external autoscaler that "adjusts the replica count through Railway's Public API" (`serviceInstanceUpdate` `numReplicas`), because "Railway does not expose per-replica utilization through the Public API." | https://docs.railway.com/guides/autoscale-horizontally |
| New replicas | "Replica changes do not rebuild your app. New replicas start from the existing deployment image, and removed replicas are drained gracefully." | autoscale guide |
| Healthchecks | "Railway does not monitor the healthcheck endpoint after the deployment has gone live." It "is only called at the start of the deployment". "The default timeout on healthchecks is 300 seconds (5 minutes)." Host `healthcheck.railway.app`. Volume services: "there will be a small amount of downtime when re-deploying a service that has a volume attached" | https://docs.railway.com/reference/healthchecks |
| Volume and replicas | Not in the docs read. Repo FACT: the sandbox runs "one replica because of the volume" | `PROJECT_CONTEXT.md:87` |
| Replica limits per service | "Replica limits allow you to limit the maximum amount of CPU and memory available to each replica." "Setting replica limits too low will cause your service to crash." | https://docs.railway.com/pricing/cost-control |
| Spend cap | Hard limit: "Once your resource usage hits the specified hard limit, all your workloads will be taken offline". Alerts at 75 %, 90 %, 100 %. | cost-control |

### 2.5 Private network across replicas

- Docs: "Every service in a project and environment gets an internal DNS name under the `railway.internal` domain"
  that "resolves to the internal IP addresses of the service". Environments created after 2025-10-16 resolve IPv4 and
  IPv6; legacy environments resolve IPv6 only.
  (https://docs.railway.com/networking/private-networking/how-it-works)
- Staff, 2026-07-08: "A DNS lookup on the service's private domain returns one record per replica, not a single
  load-balanced address."
  (https://station.railway.com/questions/does-private-networking-dns-return-one-r-595a5b07)
- Staff, 2025-11-19: "Via the private network, there is no load balancer." "we randomize the order for every DNS
  lookup". The suggested workaround is "a DNS lookup, and then randomly picking an IP to send the request to."
  (https://station.railway.com/questions/load-balancer-issue-resource-based-rout-cd4e1cac)

INFERENCE for EDGE:
- edge-bff → screener-worker and edge-bff → backtest-worker spread over replicas only as well as edge-bff's HTTP client
  re-resolves DNS. This settles 6d M-U2 in principle; per-replica shares still need to be measured.
- The private network is scoped to one project and environment. A copy placed in a second project, to escape the
  100-service cap, would need a public domain, with its egress billed and its exposure on the internet.

### 2.6 Creating services programmatically

- **Endpoint and tokens.** Endpoint "https://backboard.railway.com/graphql/v2". The tokens are account, workspace and
  project; a project token uses the `Project-Access-Token` header. (https://docs.railway.com/integrations/api)
- **Rate limits.** "100 RPH for Free customers, 1000 RPH for Hobby customers, 10000 RPH for Pro customers; custom for
  Enterprise." "10 RPS for Hobby customers; 50 RPS for Pro customers". The API answers 429 with `Retry-After`. (same
  page)
- **Create.** `mutation serviceCreate($input: ServiceCreateInput!) { serviceCreate(input: $input) { id name } }`.
  Example input: `{ projectId, name, source: { repo } }`, or `source: { image }`. Optional `branch` and `variables`.
  (https://docs.railway.com/integrations/api/manage-services)
- **Configure.** `serviceInstanceUpdate(serviceId, environmentId, input)` takes `sleepApplication`, `numReplicas`,
  `region`, `healthcheckPath`, `healthcheckTimeout` (default 300), `restartPolicyType` and `cronSchedule`. (same page)
- **Delete.** `serviceDelete(id)`: "This will delete the service and all its deployments." (same page)
- **Templates.** `templateDeployV2` (template id plus serialized config) is described only in community threads and
  third-party tools. The official API pages read here do not document it. (UNKNOWN, U7)
- **Caps that apply.** The 25-services-a-day and 100-per-project caps (§2.3) apply to programmatic creation. The CLI's
  `scale` help also says "Maximum: 50 total replicas across regions" (capacity report §2 item 5).

### 2.7 Railway Sandboxes (new; the closest thing to Fly Machines on Railway)

From https://docs.railway.com/sandboxes:
- "Sandboxes are isolated Linux VMs you create on demand, run commands in, and destroy." A sandbox can join the
  environment's private network.
- Idle timeout: 30 minutes by default on Hobby and Pro, adjustable from 1 to 120 minutes, or 0 to disable it
  (paraphrase).
- Limit: 100 per environment on Pro.
- Billing: "Sandboxes bill at VM rates, metered per second, for CPU used, memory in use, and outbound traffic."
- Intended uses: "coding agents, dependency installs, test runs, builds, and isolated code execution."

INFERENCE: sandboxes are built for untrusted, short-lived work, at 5× the RAM price. They are not a cheaper home for a
per-user copy of a market-data service.

### 2.8 Cross-check with the repository's recorded Railway facts

| Recorded fact | Repo source | Docs on 2026-10-28 | Result |
|---|---|---|---|
| Container prices, Hobby/Pro fees, Pro 42 replicas | 06d lines 32-35 | Same numbers | Agrees |
| "Internal traffic doesn't count toward egress billing" | 06d line 34 | Same sentence | Agrees |
| Random public routing, no sticky sessions, vertical scaling to plan limit, no horizontal autoscaling stated | 06d line 36 | Same; the autoscale guide now states it outright ("stays where you set it") | Agrees, stronger |
| Healthchecks at deploy only, default 300 s | 06d line 37 | Same | Agrees |
| Private network spread over replicas: UNKNOWN (M-U2) | 06d line 283 | Staff: one DNS record per replica, order randomized, no load balancer | Answered (staff, not docs) |
| Pro plan, 24 vCPU / 24 GB per replica, 50 replicas in total | capacity report §2 item 5 | Docs: 50 total (autoscale guide); per-replica 24/24 is not in the docs | Agrees; 24/24 stays a CLI reading |
| `telegram-monitor` sleeps while idle; the caller retries cold-start failures | `PROJECT_CONTEXT.md:151`; `RAILWAY_CHANGELOG.md:3722-3724` | Wake by private traffic; the first request may 502 | Agrees. Retry policy: 4 attempts, 20 s timeout, back-off 1, 2, 4 s (`apps/idx-price-cron/price_update.py:96-97, 134`) |
| Private-network wake once failed with `connection refused`; fixed by listening on IPv6 | `RAILWAY_CHANGELOG.md:3712-3718` | Legacy environments resolve IPv6 only | Agrees: a sleeping service must listen on `::` in this environment |
| Sleep window | Not recorded | 5 min (reference) or 10 min (guides) | Docs conflict. Measured: asleep within about 4.5-6.5 min (§2.10, n = 1). The cost model keeps 10 min as the conservative tail. |

### 2.9 Measurements made in this task

- **M1, FACT.** `railway status --json`, 2026-10-28 19:37 UTC:
  - `telegram-monitor` latestDeployment `status: SLEEPING` (`multiRegionConfig {"sfo": {"numReplicas": 1}}`);
  - every EDGE service `SUCCESS`;
  - 28 services in the project.
- **M2, FACT.** Three timed GETs to `https://telegram-trigger-dev.up.railway.app/health` at 19:35:34 UTC: 1.43 s, then
  0.24 s and 0.24 s (`curl` `time_starttransfer`). Control, always-on edge-bff `/health`: 0.45, 0.42 and 0.25 s.
  INFERENCE: the first call paid about 1 s more than a cold proxy connection, which is consistent with a wake. Whether
  the service was asleep before it is not known, because its state was not read first.
- **M3, controlled wake probe.** The probe reads status until `telegram-trigger` reports `SLEEPING`, then times the
  first GETs. Script: `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/wake_probe/probe.sh`.
  Log: `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/wake_probe/probe.log`. Result:
  §2.10.

What M2 and M3 measure is the platform wake floor of a tiny Python service (`python telegram_trigger.py`,
`.railway/railway.ts:106-113`). A Screener copy would add its own start: 15-25 s to `/ready` (06d.4, INFERENCE from
FACT parts). A backtest copy would add the Node start, the catalog build and an empty disk cache, giving 1.3-7 s per cold
job (`BACKTEST_END_TO_END.md` §7.4).

### 2.10 Wake probe result (FACT, measured 2026-10-28, n = 1)

| Time (UTC) | Event |
|---|---|
| before 19:36:32 | Last request to `telegram-trigger` (the M2 sequence) |
| 19:36:35, 19:38:07, 19:39:40, 19:41:13 | Status `SUCCESS` (awake) |
| 19:42:45 | Status `SLEEPING`: asleep between about 4.5 and 6.5 minutes after the last request (consistent with the reference page's "5 minutes", sampled) |
| 19:42:45.49 | First GET while `SLEEPING`: **HTTP 200 after 1.27 s** (no 502) |
| 19:42:46.77, 19:42:47.07 | Next GETs: 0.30 s, 0.24 s |
| 19:42:49 | Status `SUCCESS` again |

Reading (INFERENCE):
- The platform wake of a small Python HTTP service costs about 1 s on top of a warm request: 1.27 s against 0.24-0.30 s
  warm, and the always-on control's first call was 0.45 s.
- This sample answered 200, not the documented possible 502.
- The wake is negligible next to a Screener copy's own start (15-25 s). So the per-user cold-start cost is set by the
  application, not by Railway.
- One sample only: B1 repeats it.

---

## 3. Best practice for multi-tenant SaaS compute

### 3.1 Silo, pool, bridge (AWS)

Source: https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html

- Silo: "an architecture where tenants are provided dedicated resources" that still "relies on a shared identity,
  onboarding, and operational experience".
- Pool: "tenants share resources ... to achieve economies of scale, manageability, agility".
- Bridge: "some microservices in your architecture might be implemented with silo and others might use pool. The
  regulatory profile of a service's data and its noisy neighbor attributes might steer a microservice to a silo model.
  Meanwhile the agility, access patterns, and cost profile of another microservice could tip it toward a pool model."

Silo, pros and cons (https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/silo-isolation.html;
the whitepaper is marked "for historical reference only"):
- It "trades economies of scale and operational efficiency for compliance, business, or domain considerations".
- Pros: compliance, "No noisy neighbor concerns", tenant cost tracking, limited blast radius.
- Cons:
  - Scaling: "if you have a thousand tenants, that would likely begin to impact operational efficiency and agility".
  - Cost: "Even if these environments scale dynamically, you'll likely have periods of the day when you'll have idle
    resources".
  - Also agility, onboarding automation, and decentralized monitoring.

Pool, pros and cons (https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/pool-isolation.html):
- Pros: "your system will scale based on the actual load and activity of all of your tenants. If all the tenants are
  offline, your infrastructure costs should be minimal."
- Cons: noisy neighbour, harder cost attribution, blast radius, compliance pushback.

Tiering (https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/full-stack-silo-and-pool.html):
- Basic tenants are pooled; "premium tier tenants that are willing to pay more for the privilege of running in a silo"
  get their own stacks.
- The silos must not "allow any one-off variation or customization".

### 3.2 Azure Architecture Center

Tenancy models (https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models,
ms.date 2025-06-11):
- "Intuitively, you might want to avoid sharing any resources, but that approach quickly becomes expensive as your
  business scales".
- "If you expect your business to scale to a large number of customers, it's important to deploy shared infrastructure
  ... Deploying individual Azure resources for each customer is likely unsustainable".
- Automated single-tenant deployments: "cost efficiency is low ... If a single tenant requires a specific infrastructure
  cost, 100 tenants probably require 100 times that cost."
- B2C: "each consumer might be a separate tenant". Vertically partitioned: "single-tenant infrastructures for customers
  who require higher performance or data isolation". Horizontally partitioned: dedicated components only for the heavy
  part.

Compute (https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/compute, ms.date 2026-06-23):
- "Multitenant solutions often benefit from shared compute resources because a higher density of tenants for each
  infrastructure lowers operational costs and simplifies management."
- "Stateless components are often easy to scale out". Transient state such as "read-only in-memory caches" improves
  performance, and "If you have data that can be shared, either among tenants or among users within a single tenant,
  it's likely worth caching it" (No Caching antipattern).
- Dedicated per-tenant compute "typically incur[s] a higher cost because you have a lower density of tenants to
  resources".
- Antipatterns: noisy neighbour, cross-tenant leakage, busy front end, inelastic scaling, unnecessary statefulness.

Noisy neighbour (https://learn.microsoft.com/en-us/azure/architecture/antipatterns/noisy-neighbor/noisy-neighbor):
- Provider actions: monitor per tenant; "Apply resource governance ... quota enforcement through the Throttling pattern
  or the Rate Limiting pattern"; scale out; "Restrict the operations that tenants can perform"; QoS.

Deployment Stamps (https://learn.microsoft.com/en-us/azure/architecture/patterns/deployment-stamp, ms.date 2026-04-28):
- "each stamp serves a predefined number of tenants". "Cost: The Deployment Stamps pattern deploys multiple copies of
  your infrastructure components, which substantially increases the cost".
- Not suitable when "You can scale your system out or up within a single instance".
- Routing needs "an extra component that resolves tenants to stamps".

Cost per tenant (https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/measure-consumption):
- Estimate rather than meter when "Each tenant consumes a low percentage (say, <2%), of the overall resources" and "The
  per-tenant cost is low".
- Per-request metrics should weigh request complexity, for example "the amount of time that your application spends
  processing a specific request".

### 3.3 Per-user machine and serverless patterns

**Fly.io Machines.**
- Sources: https://docs.fly.io/launch/autostop-autostart, https://docs.fly.io/about/pricing,
  https://docs.fly.io/blueprints/per-user-dev-environments, https://docs.fly.io/blueprints/warm-pool-user-machines.
- Pricing: "A stopped or suspended Machine isn't billed for CPU or RAM. You pay only for its root file system (rootfs),
  at $0.15/GB for 30 days."
- Wake: "Resuming a suspended Machine takes a few hundred milliseconds." "A cold start takes about 2 seconds or more for
  common apps." `min_machines_running` keeps some warm.
- Per-user apps are meant for "running isolated dev environments for your users (or robots)". Fly: "Fly Machines are a
  safe execution sandbox for even the sketchiest user-generated (or LLM-generated) code."
- Many machines in one shared app: "`auto_stop` won't behave the way you expect once you scale". "with thousands of
  Machines the loop can't keep up, and most of your idle Machines stay running." Hence one app per user.
- Creating an app, volume and Machine is "a minute or more". A warm pool cuts it to "about a second".

**Cloudflare Durable Objects.**
- Sources: https://developers.cloudflare.com/durable-objects/,
  https://developers.cloudflare.com/durable-objects/platform/pricing/,
  https://developers.cloudflare.com/workers/platform/limits/.
- "Each Durable Object has a globally-unique name, which allows you to send requests to a specific object". This is the
  canonical "one object per user, room or document" building block.
- "Durable Objects that are idle and eligible for hibernation are not billed for duration". Duration is billed on "the
  128 MB of memory your Durable Object is allocated".
- Workers: "Each isolate can consume up to 128 MB of memory."
- INFERENCE: the Screener's bars alone take 229 MB of RSS after load (FACT 06d.4, `audit/benchmark.md` §2), so a
  per-user object cannot hold them. Durable Objects fit small per-user state, counters and coordination.

**AWS Lambda.** (https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)
- "Cold starts typically occur in under 1% of invocations. The duration of a cold start varies from under 100 ms to over
  1 second." You are "charged for this time".
- "The Init phase is limited to 10 seconds" on demand. Provisioned concurrency "pre-initializes execution environments".
  Lambda "terminates execution environments every few hours".
- INFERENCE: a 15-25 s Screener start does not fit on-demand init. It would need provisioned capacity, which brings back
  the idle cost.

**Google Cloud Run.** (https://docs.cloud.google.com/run/docs/tips/general)
- "You can configure minimum instances and concurrency to minimize container startup times."
- "enable startup CPU boost to temporarily increase CPU allocation during instance startup".
- "cache objects in memory if they are expensive to recreate". This is the pooled scale-to-zero model: one instance
  serves many concurrent requests.

### 3.4 When each model is recommended (synthesis, INFERENCE from 3.1-3.3)

| Model | Recommended when | Not when |
|---|---|---|
| Pool | Same code and data for all; cost and agility first; per-tenant load small (<2 %); noisy neighbour handled by quotas, lanes and QoS | Regulator or customer demands dedicated resources |
| Bridge / vertical partition | Most tenants pooled; a few premium, compliance or heavy tenants get dedicated stamps; or only the hot component is isolated | Small product without such tenants (the extra code paths are the cost) |
| Silo per tenant (stamp, app or machine per user) | Strict isolation or compliance; untrusted per-tenant code; strongly per-tenant state; few, large tenants; dedicated pricing | Many small B2C tenants sharing the same data; latency-sensitive first requests; hundreds or thousands of tenants (operations, limits, cost) |
| Per-user serverless object (Durable Object) | Small per-user state, coordination, chat rooms | Large in-memory datasets (128 MB isolate) |

---

## 4. Applied to EDGE: a copy per user for each service

### 4.1 Per service

| Service | What a per-user copy would hold | Wake cost for the user | Isolation gained | Verdict (INFERENCE) |
|---|---|---|---|---|
| screener-worker | The same publication snapshot as every other copy: 15-30 MB download, decode, 53 defaults (8.1-10.2 s CPU), RSS 0.4-0.7 GB | Platform wake (§2.9) + 15-25 s to `/ready` (06d.4), on every return after about 10 idle minutes | CPU lane only; no data is user-specific (06d.2) | Poor fit. As designed it also never sleeps: it polls `/state` every 60 s (AUDIT.md:1142), and the docs list "poll queues" among bad fits |
| backtest-worker | Node process, catalog per publication, disk cache (empty on a new copy) | Platform wake + 1.3-7 s cold job (`BACKTEST_END_TO_END.md` §7.4) | Real today: one job at a time for the whole EDGE (capacity report §3; `server.ts:20-25`) | Partly a fit. Per-user parallelism is the only real gain, and a pool with K job slots and an owner-fair claim gives the same without copies (sibling `backtest.md`) |
| terminal-api | Presign service with a Postgres pool | Platform wake (small) | None: identity and quotas are already per subscriber in Postgres (capacity report §3, P31) | Poor fit. A held Postgres connection keeps a service awake, and N pools hit `terminal_api_login` 20 (capacity report line 287) |
| Terminal page | Already runs per user in the browser; files come straight from the bucket | — | Natural per-user isolation at no server cost | Already the cheapest "per-user compute" |

### 4.2 Cost: silo against pool, Screener only (INFERENCE)

Calculation: `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/silo_calc/cost.py`.

| Input | Value | Source |
|---|---|---|
| RAM and CPU prices | Container rates of §2.2 | FACT |
| RSS of an awake copy | 0.6 GB | 06d.4 |
| CPU per wake | 20 vCPU·s | 06d.9 `c_refresh` |
| Trading days a month | 21 | ASSUMPTION |
| Awake tail after the last request | 10 min | docs upper bound |
| Pool | Peak concurrency 30 % of users, 37 editing users per replica, floor of 2 replicas | 6d, P32 |

| Users N | Silo, light (2×15 min/day) | Silo, medium (4×30 min/day) | Silo, market hours (7 h/day) | Pool 24/7 (replicas) | Pool asleep outside 10 h × 21 d |
|---|---|---|---|---|---|
| 1 | 0.15 | 0.48 | 1.25 | 11.98 (2) | 3.49 |
| 10 | 1.52 | 4.79 | 12.55 | 11.98 (2) | 3.49 |
| 30 | 4.56 | 14.36 | 37.64 | 11.98 (2) | 3.49 |
| 100 | 15.20 | 47.87 | 125.48 | 11.98 (2) | 3.49 |
| 500 | 76.01 | 239.33 | 627.40 | 29.94 (5) | 8.73 |

Each user also pays cold starts: 42 a month (light), 84 (medium) or 21 (market hours), each 15-25 s plus the wake.

Reading:
- Copies beat a 24/7 two-replica pool only for very few, light users.
- They lose to a pool that sleeps outside trading hours at every size.
- They lose by 10-70× once users overlap during market hours.
- The per-user CPU for screens themselves is the same in both models; the silo adds the repeated init.
- Backtest copies: about USD 0.25 per user a month at the medium profile (0.32 GB awake). Cheap, but each cold job is
  the 1.3-7 s figure plus the wake.

### 4.3 Railway-specific blockers for "one service per user" (FACT limits, INFERENCE consequences)

1. **Capacity:** 100 services a project (§2.3), 28 already used. That leaves 72 users at 1 copy each, 36 at 2, 24 at 3.
   More users need more projects, which lose the private network (§2.5): a public domain per copy, auth on every copy,
   billed egress.
2. **Creation rate:** 25 new services a day for a "new" account, and it "cannot be raised" (staff). A signup spike
   stalls onboarding unless copies are pre-created, a warm pool as on Fly.io (§3.3).
3. **Deploy fan-out:** every change to the worker must reach N copies. Today two of the three services build from
   GitHub watch paths or a CLI upload (`.railway/railway.ts:158-190`), so N copies mean N builds. Image-based copies
   would need one `serviceInstanceRedeploy` per copy within 10,000 requests an hour (§2.6). Concurrent build limits:
   UNKNOWN (U6).
4. **Routing:** edge-bff would need a user → copy table and per-copy keys, since `BACKTEST_WORKER_KEY` and similar
   variables are set per service. This is the "tenant mapping" component of the Deployment Stamps pattern (§3.2).
5. **Sleep fidelity:** a copy sleeps only if it is fully quiet for 5-10 minutes. No `/state` polling, no Postgres pool,
   no telemetry, and it must listen on IPv6 (§2.8). A copy that never sleeps costs the full idle floor per user: USD 4-7
   a month for a Screener copy.
6. **No per-user replica either:** replicas share one service. Public routing is random, there are no sticky sessions,
   and private DNS returns all replicas in random order (§2.4, §2.5). So "replica per user" is not possible natively.
7. **Observability:** Railway metrics are per service. N copies multiply dashboards, alerts and logs. This is the
   "Decentralized management and monitoring" con of AWS's silo model.

---

## 5. Recommendation (PROPOSED, for the user's decision)

1. **Keep one pool per service and isolate users logically.** This is the design already in 6d and the capacity report.
   - **screener-worker:** stateless replicas, one snapshot per publication, threads before replicas,
     `SCREENER_OWNER_INFLIGHT` lanes.
   - **backtest-worker:** K job slots or replicas with the round-robin claim over owners (`backtest.py:516-526`) and
     `BACKTEST_QUEUED_PER_OWNER` 3.
   - **terminal-api:** per-user subscriber identity and quotas (P31).
   - This matches AWS's pool model and Azure's compute guidance for many small tenants with shared data.
2. **Get "no cost while idle" from the pool, not from copies.**
   - (a) Remove idle outbound traffic from the pooled service, or restrict it to market hours. For the Screener, check
     `/state` on request with the 60 s guard the backtest-worker already uses (AUDIT.md:137), instead of a timer.
   - (b) Enable Serverless. It needs a redeploy (§2.1).
   - (c) Pre-warm with a small Railway cron before IDX open (for example 08:30 WIB = 01:30 UTC; minimum cron interval
     5 min). The cron calls `/ready` over the private network, which wakes the service.
   - (d) edge-bff retries the first 502 with a short back-off, as `price_update.py:96-134` already does, and the page
     shows its waiting state.
   - Cost: §4.2's last column, about USD 3.5 a month for two Screener replicas instead of 12. One cold start a day
     instead of one per user and session.
   - Trade-off: a user arriving outside the warm window waits through the Screener start (15-25 s). Whether to keep the
     pool awake 24/7 for a few dollars a month is the user's call.
3. **Shrink the cold start once for everyone.** Precomputing the defaults per publication upstream (the publisher writes
   a ready snapshot once) would cut a wake to download + decode, about 6-10 s. This is a lead for the parallel runtime
   design (`RUNTIME.md`), not a decision.
4. **Silo only as an explicit exception (bridge).**
   - A paying "dedicated" tier, or a tenant with a compliance requirement, gets its own stamp: the same image and
     version (AWS: no one-off variation).
   - Per-job isolation for heavy backtests (Railway Sandboxes or Fly Machines) only if measurement shows pooled slots
     cannot meet the wait target. Sandboxes cost 5× the RAM price (§2.7).
5. **Cost per user in the pool:** estimate it, don't meter it. Use per-request CPU time (`timings_ms`) by owner, which
   Azure recommends while each tenant uses under 2 % of the deployment. The capacity report's usage ledger is the place
   for it.

### Benchmarks to settle it (PROPOSED; each one that creates or changes a Railway service needs the user's approval)

| Id | Measures | How | Decides |
|---|---|---|---|
| B1 | Platform wake floor | §2.9 M3; repeat 10× over a day on `telegram-trigger` (read-only) | Retry and back-off on edge-bff; whether the floor matters next to the app start |
| B2 | Pooled Screener cold start to `/ready`, and the first screen | 6d S24 on a test copy with Serverless on | Pre-warm schedule; whether item 3 is worth it |
| B3 | Billing while asleep | Usage API (`usage(..., groupBy SERVICE_ID)`, as in the capacity report §2.2) over 24 h for `telegram-monitor` (asleep) | Confirms "no compute charges" for RAM (U1) |
| B4 | Pool fairness under many owners | 6d S21 (1, 10, 50 synthetic owners) and the sibling backtest queue model | K, replicas, lanes |
| B5 | Silo control: time to create and serve one copy | `serviceCreate` + `serviceInstanceUpdate` + first `/ready` on a throwaway service, then `serviceDelete` | Only if the user wants the silo option measured; creates a service, so it needs approval |

---

## 6. UNKNOWN

| Id | What | How to settle |
|---|---|---|
| U1 | Whether RAM is billed at all while asleep. The guide says "no compute charges" and names RAM and CPU as the usage in the sentence before it, but gives no explicit memory sentence. | B3 |
| U2 | Typical Railway wake time; no number is published. One sample: about 1 s (§2.10) | B1 (repeat, different hours) |
| U3 | Whether a woken container keeps its ephemeral disk (backtest disk cache, `SCREENER_CACHE_DIR`) | Test on a sleeping test service: write a marker file, let it sleep, wake it |
| U4 | Whether the 100-service cap can be raised for this account. One user-reported case went to 150 after support (search summary, not verified) | Ask Railway support |
| U5 | Whether this account still counts as "new" for the 25-a-day cap | Ask Railway support, or only when needed |
| U6 | Concurrent builds and build-minute limits for N copies | Railway support or docs |
| U7 | Official status of `templateDeployV2` | Railway API reference |
| U8 | Whether traffic reaches a newly added replica before its healthcheck passes (6d M-U3) | 6d S24 |

## 7. Sources (all read 2026-10-28)

Railway:
- https://docs.railway.com/reference/app-sleeping
- https://docs.railway.com/deployments/serverless
- https://docs.railway.com/guides/cut-idle-costs-serverless
- https://docs.railway.com/pricing/cost-control
- https://docs.railway.com/reference/pricing
- https://docs.railway.com/reference/pricing/plans
- https://docs.railway.com/reference/scaling
- https://docs.railway.com/deployments/scaling
- https://docs.railway.com/guides/scaling-your-application
- https://docs.railway.com/guides/autoscale-horizontally
- https://docs.railway.com/reference/healthchecks
- https://docs.railway.com/networking/private-networking/how-it-works
- https://docs.railway.com/integrations/api
- https://docs.railway.com/integrations/api/manage-services
- https://docs.railway.com/integrations/api/api-cookbook
- https://docs.railway.com/sandboxes
- https://docs.railway.com/volumes

Railway community (staff replies or quoted error texts):
- https://station.railway.com/questions/25-services-per-day-19e355a8
- https://station.railway.com/questions/increase-project-service-limit-from-100-80621cdd
- https://station.railway.com/questions/does-private-networking-dns-return-one-r-595a5b07
- https://station.railway.com/questions/load-balancer-issue-resource-based-rout-cd4e1cac
- https://station.railway.com/questions/i-m-developing-a-multi-tenanting-applica-7200c926

AWS:
- https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html
- https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/silo-isolation.html
- https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/pool-isolation.html
- https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/full-stack-silo-and-pool.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html

Azure:
- https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models
- https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/compute
- https://learn.microsoft.com/en-us/azure/architecture/antipatterns/noisy-neighbor/noisy-neighbor
- https://learn.microsoft.com/en-us/azure/architecture/patterns/deployment-stamp
- https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/measure-consumption

Fly.io:
- https://docs.fly.io/launch/autostop-autostart
- https://docs.fly.io/about/pricing
- https://docs.fly.io/blueprints/per-user-dev-environments
- https://docs.fly.io/blueprints/warm-pool-user-machines

Cloudflare:
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://developers.cloudflare.com/durable-objects/platform/limits/
- https://developers.cloudflare.com/workers/platform/limits/

Google Cloud:
- https://docs.cloud.google.com/run/docs/tips/general

Repository: `.railway/railway.ts`, `PROJECT_CONTEXT.md`, `RAILWAY_CHANGELOG.md`, `BACKTEST_END_TO_END.md`,
`verification/screener/AUDIT.md`, `verification/edge_multiuser/capacity_fairness_scale_cost.md`,
`apps/idx-price-cron/price_update.py`, `apps/telegram-trigger/telegram_trigger.py`; and the scratchpad report
`report/06d_multi_user_scale_cost.md`.
