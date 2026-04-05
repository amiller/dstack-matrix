# dstack-matrix Architecture Proposal: Scaling to 1000 Users

**Date:** April 2, 2026
**Author:** Hermes Agent (research + proposal)
**Status:** Draft for review

---

## Executive Summary

This document proposes a phased scaling path for dstack-matrix, a Synapse-based Matrix homeserver running inside a Phala Network TEE (Trusted Execution Environment). The goal is to grow from the current 3 users to 1000 users while maintaining the TEE security guarantees and staying within Phala's available instance types.

**Key finding:** Synapse (not Conduwuit) is the right server software for this target scale, but it needs worker processes and Redis to get there. The good news: Synapse workers communicate only via PostgreSQL and Redis pub/sub (no shared memory), so they can run in separate TEE instances.

---

## Current Architecture

```
                     Internet
                        |
               dstack gateway (TLS)
                        |
         ┌──────────────┴──────────────┐
         |        1 TEE instance        |
         |    tdx.small (1vCPU, 2GB)    |
         |                              |
         |  ┌────────────────────────┐  |
         |  │ nginx (:8008)          │  |
         |  │   └──> Synapse (:8009) │  |
         |  ├────────────────────────┤  |
         |  │ Element Web (:8443)    │  |
         |  ├────────────────────────┤  |
         |  │ PostgreSQL (:5432)     │  |
         |  └────────────────────────┘  |
         └──────────────────────────────┘
```

**Resources:** 1 vCPU, 2 GB RAM (~$0.058/hr = ~$42/month)
**Containers:** 3 (synapse, postgres, element)
**Cost:** ~$42/month
**Estimated capacity:** ~10-20 concurrent users

**Current features:**
- GitHub OAuth login
- Registration tokens (invite codes)
- Federation with matrix.org (verified: @socrates1024:matrix.org is active)
- E2EE support (Olm/Megolm)
- Admin API for user/room/token management
- Custom Docker image with nginx (fixes X-Forwarded-Proto gap)

---

## Why Synapse, Not Conduwuit

| Feature | Synapse | Conduwuit |
|---------|---------|-----------|
| OAuth/OIDC (GitHub login) | Yes | **No** |
| Registration tokens | Yes | **No** |
| Admin API completeness | Full | Basic |
| Sliding Sync | Production-ready | Experimental |
| Scaling model | Multi-worker | Single-process only |
| Max practical users | 10,000+ | ~500 |
| Resource usage (3 users) | ~500MB RAM | ~50MB RAM |
| Resource usage (1000 users) | 16-32GB RAM across workers | N/A (can't scale) |

**Verdict:** Conduwuit's lack of OAuth, registration tokens, and single-process ceiling make it a non-starter for 1000 users. Synapse is heavier but has every feature needed. The resource overhead is manageable with workers.

---

## Synapse Worker Architecture Explained

### The Problem: /sync is Expensive

When a Matrix client asks "what changed since I last checked?" (`GET /sync`), Synapse must:
1. Find all new events since the user's last sync token
2. Compute room state at each event position
3. Apply redactions, visibility filters, aggregation (reactions, edits)
4. Bundle it all into a response

This is ~60-70% of Synapse's CPU workload. For 3 users it's trivial. For 1000 users all syncing simultaneously, it's the bottleneck.

### Workers: Divide and Conquer

Synapse supports splitting into multiple processes (workers), each handling a subset of endpoints. They share state through:
- **PostgreSQL** -- shared database (all workers connect to the same cluster)
- **Redis pub/sub** -- real-time event replication (worker A writes an event, publishes to Redis, worker B updates its cache)

There is NO shared memory. Workers are independent processes that communicate via TCP.

### Worker Types

| Worker | What It Does | Scales Horizontally? |
|--------|-------------|---------------------|
| **Synchrotron** | Handles `/sync` requests. Maintains per-user state caches. Most CPU-intensive. | Yes -- run N behind load balancer with sticky sessions |
| **Event Persister** | Writes new events to PostgreSQL. Critical write path. | Yes -- can shard by room |
| **Federation Sender** | Sends outbound events to other homeservers. | Yes -- can shard by destination server |
| **Federation Reader** | Handles inbound federation traffic (`/send`, `/pull`, `/event`). | Yes |
| **Client Reader** | Handles client API reads (room info, profiles, public rooms). | Yes |
| **Media Repository** | Handles uploads, downloads, thumbnails. Can use S3. | Yes |
| **Pusher** | Sends push notifications (FCM/APNs). | Limited |
| **Background Worker** | Cleanup, stats, maintenance. | No -- single instance |

All workers now use `synapse.app.generic_worker` with endpoint-based routing. The old separate app names (synchrotron, etc.) are deprecated.

### How Routing Works

A reverse proxy (nginx/haproxy) in front routes by URL path:

```
/_matrix/client/*/sync        --> synchrotron workers
/_matrix/client/*/messages    --> synchrotron workers
/_matrix/client/*             --> client reader workers
/_matrix/federation/*         --> federation reader workers
/_matrix/media/*              --> media workers
everything else               --> main process
```

### What is Sliding Sync?

Traditional `/sync` returns ALL data for ALL rooms. If you're in 200 rooms, every sync returns data for all 200. Initial sync can be megabytes and take minutes. This is why Element (classic) feels slow.

Sliding Sync (MSC3575) lets the client say: "give me rooms 0-20 sorted by recent activity, and only the last 5 messages per room." As you scroll, the window slides. Initial sync goes from minutes to sub-second.

Synapse supports this natively (v1.113+). Conduwuit has experimental support. Element X uses it exclusively. For 1000 users, sliding sync dramatically reduces server load because clients request far less data.

---

## Proposed Architecture: Three Phases

### Phase 1: Single-TEE Scaling (~50-100 users)

Upgrade the single TEE instance and add Redis.

```
                     Internet
                        |
               dstack gateway (TLS)
                        |
         ┌──────────────┴──────────────────┐
         |     1 TEE instance               |
         |  tdx.large (4vCPU, 8GB)          |
         |                                  |
         |  ┌──────────────────────────┐    |
         |  │ nginx (reverse proxy)    │    |
         |  │   routes /sync, /feder., │    |
         |  │   /media to workers      │    |
         |  ├──────────────────────────┤    |
         |  │ Synapse main process     │    |
         |  │ (registration, admin,    │    |
         |  │  event persistence)      │    |
         |  ├──────────────────────────┤    |
         |  │ Synchrotron worker       │    |
         |  │ (handles /sync)          │    |
         |  ├──────────────────────────┤    |
         |  │ Federation sender worker  │    |
         |  ├──────────────────────────┤    |
         |  │ Redis (pub/sub bus)      │    |
         |  ├──────────────────────────┤    |
         |  │ PostgreSQL               │    |
         |  ├──────────────────────────┤    |
         |  │ Element Web              │    |
         |  └──────────────────────────┘    |
         └──────────────────────────────────┘
```

**Changes from current:**
- Upgrade from `tdx.small` (1 vCPU, 2GB) to `tdx.large` (4 vCPU, 8GB)
- Add Redis container
- Run Synapse with 1 synchrotron worker + 1 federation sender worker
- Update nginx to route `/sync` to the synchrotron worker

**docker-compose.yaml additions:**
```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped

  synapse-main:
    # existing synapse config, plus:
    environment:
      - SYNAPSE_WORKER=synapse.app.homeserver
    # connects to redis + postgres

  synapse-synchrotron:
    image: ghcr.io/amiller/dstack-matrix
    environment:
      - SYNAPSE_WORKER=synapse.app.generic_worker
    # config points to same redis + postgres
    # nginx routes /sync here

  synapse-federation-sender:
    image: ghcr.io/amiller/dstack-matrix
    environment:
      - SYNAPSE_WORKER=synapse.app.generic_worker
    # handles outbound federation
```

**Cost:** ~$168/month ($0.232/hr)
**Estimated capacity:** 50-100 concurrent users
**Complexity:** Medium -- all in one container, workers are separate processes

**Deployment considerations:**
- The Synapse signing key stays on this TEE (only main process needs it)
- GitHub OAuth secret stays in secrets.env (same injection pattern)
- Registration tokens still work (admin API is on main process)
- Redis does NOT need persistence for this use case (it's a message bus, not a data store)

---

### Phase 2: Multi-TEE with Shared Database (~500 users)

Split workers across multiple TEE instances, sharing a PostgreSQL database.

```
                     Internet
                        |
               dstack gateway (TLS)
                        |
         ┌──────────────┼──────────────────────────┐
         |              |                            |
    TEE 1: Main      TEE 2: Synchrotrons       TEE 3: Federation
    tdx.large        tdx.large                  tdx.medium
    (4vCPU, 8GB)     (4vCPU, 8GB)               (2vCPU, 4GB)
         |              |                            |
    ┌────┴────┐    ┌────┴────┐                  ┌───┴────┐
    │ nginx   │    │ synch. 1│                  │ fed    │
    │ main    │    │ synch. 2│                  │ reader │
    │ postgres│    │         │                  │ sender │
    │ redis   │    └─────────┘                  └────────┘
    │ element │         |                           |
    └─────────┘         |                           |
         |              +-------------+--------------+
         |                            |
         └──── all connect to ────────┘
              Postgres + Redis on TEE 1
```

**Changes from Phase 1:**
- Synchrotron workers move to a separate TEE instance
- Federation workers move to a separate TEE instance
- PostgreSQL and Redis stay on TEE 1
- Workers on TEE 2/3 connect to PostgreSQL and Redis on TEE 1 over the dstack internal network

**Key question:** Can dstack TEE instances communicate with each other over an internal network? This needs verification. If not, workers would need to connect through the gateway, adding latency.

**Cost:** ~$168 + $168 + $84 = ~$420/month
**Estimated capacity:** 300-500 concurrent users
**Complexity:** High -- multi-TEE networking, shared database access

**TEE-specific considerations:**
- The signing key stays on TEE 1 only
- PostgreSQL connections between TEEs should use TLS (PostgreSQL supports it natively)
- Redis connections between TEEs: Redis 6+ supports TLS
- Attestation can verify each TEE is running the expected worker image
- The database contains all message content (for non-E2EE rooms) -- it's the highest-value target and benefits most from TEE protection

**Media storage scaling:**
At 500 users, media uploads become significant. Options:
- Keep media in Synapse's volume on TEE 1 (simple, limited by disk)
- Use Synapse's `media_storage_providers` to offload to S3-compatible storage
- Dedicated media TEE with large disk

---

### Phase 3: Full Production Scale (~1000+ users)

Full worker deployment with PostgreSQL replicas and horizontal synchrotron scaling.

```
                     Internet
                        |
               dstack gateway (TLS)
                        |
         ┌──────────────┼────────────────┐
         |              |                |
    TEE 1: Core      TEE 2: Sync      TEE 3: Federation
    tdx.xlarge       tdx.2xlarge       tdx.large
    (8vCPU, 16GB)    (16vCPU, 32GB)    (4vCPU, 8GB)
         |              |                |
    ┌────┴────┐    ┌────┴────┐      ┌───┴──────┐
    │ nginx   │    │ synch. 1│      │ fed read  │
    │ main    │    │ synch. 2│      │ fed send 1│
    │ event   │    │ synch. 3│      │ fed send 2│
    │ persist │    │ synch. 4│      │ client rd │
    │ redis   │    └─────────┘      └──────────┘
    │ pgBounc │         |                |
    │ element │         +--------+-------+
    └─────────┘                  |
         |            TEE 4: Database
         └───────> tdx.xlarge (8vCPU, 16GB)
                    ┌───────────────────┐
                    │ PostgreSQL primary │
                    │ + read replica     │
                    │ media storage      │
                    └───────────────────┘
```

**Worker count:** ~10-12 processes across 4 TEE instances

**New components:**
- **PgBouncer** on TEE 1 -- connection pooling (Synapse opens many PG connections)
- **PostgreSQL read replica** -- synchrotrons read from replica, reducing primary load
- **4 synchrotron workers** -- each handles ~250 users' /sync requests
- **Sharded federation senders** -- split outbound federation by destination server
- **Event persister** on main process (or dedicated worker if write load is high)

**Cost:** ~$464 + $928 + $232 + $464 = ~$2,088/month
**Estimated capacity:** 1000-2000 concurrent users
**Complexity:** Very high

**Resource estimates per 1000 users:**
- Total CPU: ~20-30 cores across all workers
- Total RAM: ~32-48 GB (synchrotrons are memory-hungry due to caches)
- PostgreSQL: 8-16 cores, 16-32 GB RAM, NVMe storage
- Redis: 2-4 GB RAM (it's a message bus, not a data store)
- Storage: ~50-100 GB for database, ~200+ GB for media (depends on usage)

---

## Registration and Onboarding at Scale

### Current System
- Registration tokens (`dstack-invite`, `openclaw-invite`) with use limits
- GitHub OAuth for social login
- No email verification required
- Admin approval not required

### Scaling Considerations

At 1000 users, registration management becomes important:

**Option A: Stay with registration tokens**
- Create tokens programmatically via Synapse admin API
- Distribute tokens through your onboarding flow (website, Discord, etc.)
- Tokens can have use limits and expiry times
- Simple, no email infrastructure needed
- Downside: tokens can be shared/leaked

**Option B: GitHub OAuth only**
- Remove token-based registration entirely
- Every user must have a GitHub account
- Can add org membership checks (require users to be in a specific GitHub org)
- Upside: strong identity, no spam
- Downside: excludes non-GitHub users

**Option C: Add email verification**
- Synapse supports `enable_registration_without_verification: false`
- Requires an SMTP server or email service
- Can verify email ownership before allowing registration
- Most traditional approach

**Option D: TEE-attested registration**
- Research opportunity: require users to prove they're running in a TEE to register
- Uses Phala's remote attestation as a registration gate
- Could issue registration tokens only after successful attestation
- Novel approach, no existing Matrix implementation

**Recommendation:** Start with Option A (tokens) for Phase 1-2. Add Option C (email) for Phase 3. Option D is a research project worth exploring separately.

---

## Session Management

### What Synapse Provides

| Capability | User Self-Service | Admin API |
|---|---|---|
| View own devices | Yes (`GET /_matrix/client/v3/devices`) | Yes (`GET /_synapse/admin/v2/users/{id}/devices`) |
| Delete own device | Yes (`DELETE /_matrix/client/v3/devices/{id}`) | Yes (`DELETE /_synapse/admin/v2/users/{id}/devices/{id}`) |
| Force-logout all sessions | No direct API | Yes (delete all devices for a user) |
| View access tokens | No | No (hashed in DB) |
| Shadow-ban a user | No | Yes (`PUT /_synapse/admin/v1/users/{id}/shadow_ban`) |
| Deactivate user | No | Yes (`POST /_synapse/admin/v1/deactivate/{id}`) |
| Reset password | No | Yes (`POST /_synapse/admin/v1/reset_password/{id}`) |
| Whois (session info) | No | Yes (`GET /_synapse/admin/v1/whois/{id}`) |

### For a TEE Matrix Server

Session management matters more in a TEE context because:
1. **No operator access** -- you can't SSH in and inspect sessions (well, you can via phala ssh, but the data is encrypted in memory)
2. **Admin API becomes critical** -- it's your primary management interface
3. **Compromised accounts** -- you need the ability to quickly force-logout and reset passwords
4. **Audit trail** -- Synapse logs device creation, last seen IP, timestamps

**Recommendation:** Build a lightweight admin dashboard (could be another artifact served from nginx, like the matrix-monitor) that wraps the Synapse admin API for common operations:
- List users and their devices
- Force-logout a user (delete all devices)
- Create/revoke registration tokens
- Deactivate a user
- View federation status

This could be a simple static HTML page that calls the Synapse admin API with an admin access token.

---

## TEE-Specific Architecture Notes

### What Runs Where

| Component | TEE Required? | Why |
|---|---|---|
| Synapse main process | Yes | Handles signing key, registration, event persistence |
| Synchrotron workers | Recommended | Holds decrypted room state in memory |
| Federation workers | Recommended | Processes inbound/outbound federation traffic |
| PostgreSQL | Strongly recommended | Stores all message content (non-E2EE rooms) |
| Redis | Nice to have | Message bus, contains no persistent secrets |
| Element Web | Not needed | Static files, no server-side state |
| nginx | Not needed | Just routing, no sensitive data |
| Media storage | Recommended | Stores uploaded files, images |

### Attestation Implications

- **Single TEE (Phase 1):** Simple attestation story. One enclave, one Docker image digest to verify.
- **Multi-TEE (Phase 2-3):** Each TEE has its own attestation. A client verifying the system would need to check all TEEs. The signing key TEE is the most critical to verify.
- **Code updates:** Any change to the Docker image changes the attestation digest. Users verifying attestation would see the update. Consider a "digest pinning" policy where you announce planned updates.

### Signing Key Protection

The Synapse signing key (`/data/signing.key`) is the most sensitive asset. It proves your server's identity to the federated network. In a TEE:
- The key is generated inside the enclave and never leaves encrypted memory
- Even you (the operator) cannot extract it
- If the TEE is destroyed/recreated, you'd need to generate a new key, which means a new server identity (and all federated relationships break)
- This is why DEPLOY.md says "never delete + redeploy" -- the app ID and signing key are tied to the CVM

With workers, only the main process needs the signing key. Synchrotron and federation reader workers don't sign events.

---

## Cost Summary

| Phase | Users | TEE Instances | Monthly Cost | Key Upgrade |
|-------|-------|---------------|-------------|-------------|
| Current | 3 | 1x tdx.small | ~$42 | -- |
| Phase 1 | 50-100 | 1x tdx.large | ~$168 | Add workers + Redis |
| Phase 2 | 300-500 | 3x mixed | ~$420 | Multi-TEE, shared DB |
| Phase 3 | 1000+ | 4x mixed | ~$2,088 | Full production scale |

Note: Phase 3 cost is significant (~$25K/year). At that scale you'd want to evaluate whether TEE-provided confidentiality justifies the cost premium over a conventional VPS deployment with full-disk encryption.

---

## Open Questions

1. **Can dstack TEE instances communicate internally?** Phase 2+ depends on workers connecting to PostgreSQL and Redis across TEEs. Need to verify internal networking capabilities.

2. **Redis in a TEE?** Redis is ephemeral (no persistent data) but sits on the replication path. If a non-TEE Redis is compromised, an attacker could inject fake replication events. Worth evaluating.

3. **Media storage strategy.** At 1000 users, media will dominate storage. Need to decide between local volumes, S3-compatible storage, or a dedicated media TEE.

4. **Sliding sync proxy.** Element X requires sliding sync. Synapse supports it natively, but it may need tuning for performance at scale.

5. **Monitoring.** No observability stack exists yet. At 1000 users you'll need metrics (Prometheus + Grafana), logging aggregation, and alerting. This could run outside the TEE since it doesn't handle sensitive data.

6. **Backup strategy.** PostgreSQL backups need to be encrypted (since the DB contains message content). TEE-encrypted backups or client-side encryption would be needed.

---

## Recommended Next Steps

1. **Phase 1 implementation** -- add Redis + synchrotron worker to the existing single-TEE setup. This is the highest-impact change with the lowest risk. Can be done by updating the Dockerfile and docker-compose.yaml.

2. **Test multi-TEE networking** -- spin up two small TEE instances and verify PostgreSQL and Redis connectivity between them. This determines whether Phase 2 is feasible.

3. **Build an admin dashboard** -- a simple web UI for user management, token management, and federation status. Served from the existing nginx alongside Element.

4. **Evaluate Conduwuit for small deployments** -- if you have use cases for small (under 100 user) TEE Matrix servers where the tiny resource footprint matters, Conduwuit is worth tracking. Check back in 6 months for OAuth/registration token support.

5. **Research TEE-attested registration** -- explore using Phala's attestation as a registration gate. This is the novel contribution that makes TEE Matrix servers interesting beyond "Synapse in a TEE."
