# dstack-matrix deploy notes

## Current deployment

| | |
|---|---|
| CVM name | `dstack-matrix-v2` |
| App ID | `4292190d21a00e7cde508b9d7365ea7a9e3cfa18` |
| CVM UUID | `60f4f282-f1a0-4fee-8812-c14ee5978a5b` |
| Gateway | `dstack-pha-prod7.phala.network` |
| Synapse | `https://4292190d21a00e7cde508b9d7365ea7a9e3cfa18-8008.dstack-pha-prod7.phala.network` |
| Element | `https://4292190d21a00e7cde508b9d7365ea7a9e3cfa18-8443.dstack-pha-prod7.phala.network` |
| Image | `ghcr.io/amiller/dstack-matrix` (must be public on GHCR) |
| GitHub OAuth | Client ID `Ov23liJJzPVzxe4e0TSa`, callback at `.../_synapse/client/oidc/callback` |
| Admin | `admin` / `dstack-matrix-admin` |
| Reg tokens | `dstack-invite` (10 uses), `openclaw-invite` (5 uses) |

## How to deploy / update

```bash
# 1. Build and push image
docker build -t ghcr.io/amiller/dstack-matrix:latest .
docker push ghcr.io/amiller/dstack-matrix:latest

# 2. Get the new digest
docker inspect ghcr.io/amiller/dstack-matrix:latest --format '{{index .RepoDigests 0}}'

# 3. Update digest in docker-compose.yaml

# 4. Deploy and restart (BOTH steps required)
phala deploy --cvm-id dstack-matrix-v2 -c docker-compose.yaml -e secrets.env
phala cvms restart 60f4f282-f1a0-4fee-8812-c14ee5978a5b
```

## Architecture

```
Internet → dstack gateway (TLS termination) → nginx (:8008) → Synapse (:8009)
                                             → Element (:8443)
                                             → Postgres (:5432)
```

The custom Docker image (`ghcr.io/amiller/dstack-matrix`) bundles three things:
1. **Synapse** — listens on port 8009
2. **nginx** — listens on port 8008, proxies to Synapse, adds `X-Forwarded-Proto: https`
3. **entrypoint.sh** — runs `sed` to inject `GITHUB_OAUTH_SECRET` from env var into homeserver.yaml at startup

### Why nginx is needed

The dstack gateway terminates TLS but does NOT set `X-Forwarded-Proto: https`. Without it, Synapse thinks every request is HTTP and tries to redirect SSO/OIDC endpoints to HTTPS, creating an infinite redirect loop. The nginx proxy adds the missing header.

### Why configs are baked into the image

Docker compose inline `configs: content:` blocks don't reliably update when doing `phala deploy --cvm-id`. The compose file updates but running containers keep stale config files. Building configs into the image and pinning by digest ensures the CVM always gets the right config.

### Secret injection

The GitHub OAuth client secret cannot be in docker-compose.yaml (compose files are public in dstack — they're hashed for attestation). Instead:
- `homeserver.yaml.tmpl` has placeholder `__GITHUB_OAUTH_SECRET__`
- `secrets.env` has the real secret: `GITHUB_OAUTH_SECRET=...`
- `phala deploy -e secrets.env` encrypts and injects it as an env var
- `entrypoint.sh` runs `sed` to substitute the placeholder at container startup

### Persistence

Named volumes survive restarts:
- `synapse-data` → `/data` (signing key, media uploads, pid file)
- `postgres-data` → `/var/lib/postgresql/data` (all Matrix data)

## Files

| File | Purpose |
|---|---|
| `docker-compose.yaml` | Compose for dstack deploy (3 services + 1 inline config for Element) |
| `Dockerfile` | Custom image: Synapse + nginx + entrypoint |
| `homeserver.yaml.tmpl` | Synapse config template with `__GITHUB_OAUTH_SECRET__` placeholder |
| `nginx.conf` | Adds `X-Forwarded-Proto: https` header |
| `entrypoint.sh` | Secret substitution then starts nginx + Synapse |
| `log.config` | Synapse logging (WARNING level) |
| `secrets.env` | GitHub OAuth secret (DO NOT COMMIT) |
| `matrix-chat.sh` | CLI helper for send/read messages |

## Pitfalls we hit

### 1. Gateway is prod7, not prod9
The tutorial docs reference prod9 but the working gateway is `dstack-pha-prod7.phala.network`. Check with `phala nodes list`.

### 2. Never delete + redeploy
`phala deploy --cvm-id <name>` upgrades in place, preserving the app ID and gateway URL. Deleting and redeploying generates a new app ID, breaking all URLs, federation, OAuth callbacks, and any stored state.

### 3. Deploy doesn't restart containers
`phala deploy --cvm-id` updates the compose definition but does NOT restart running containers. Always follow with `phala cvms restart <uuid>`.

### 4. Inline configs don't update on upgrade
Docker compose `configs: content:` blocks are cached. Even after deploy + restart, containers may keep old config files. Bake configs into your Docker image instead.

### 5. Chicken-and-egg with app ID
The app ID (and gateway URL) is only known after the first deploy. Services that need their own public URL in config (like Synapse's `server_name`) require: deploy with placeholder → get app ID → update config → redeploy.

### 6. Synapse permission issues
The Synapse Docker image runs as UID 991 by default. On dstack, named volumes may not be writable by this user. Running as `user: "0:0"` (root) or using the custom image (which sets `USER root`) fixes this.

### 7. Synapse report_stats
`SYNAPSE_REPORT_STATS=no` env var is ignored when a custom `homeserver.yaml` is provided. Must set `report_stats: false` in the YAML config itself.

### 8. nginx $variables in compose
Docker compose interpolates `$host` and `$remote_addr` in `configs: content:` blocks, breaking nginx config. Escaping with `$$host` gets processed again by nginx's own `envsubst` script. Solution: bake nginx.conf into the image.

### 9. GHCR images default to private
New container images pushed to `ghcr.io` are private by default. The CVM will silently fail to pull them. Make public at: `https://github.com/users/amiller/packages/container/dstack-matrix/settings`

### 10. Pin images by digest
Phala does NOT re-pull when you push to the same tag. Always pin by `@sha256:...` digest in docker-compose.yaml.

## Admin API cheatsheet

```bash
HS=https://4292190d21a00e7cde508b9d7365ea7a9e3cfa18-8008.dstack-pha-prod7.phala.network

# Register user via shared secret
NONCE=$(curl -s "$HS/_synapse/admin/v1/register" | python3 -c "import sys,json; print(json.load(sys.stdin)['nonce'])")
MAC=$(python3 -c "import hmac,hashlib; print(hmac.new(b'dstack-matrix-secret', '$NONCE\x00USERNAME\x00PASSWORD\x00notadmin'.encode(), hashlib.sha1).hexdigest())")
curl -X POST "$HS/_synapse/admin/v1/register" -H 'Content-Type: application/json' \
  -d "{\"nonce\":\"$NONCE\",\"username\":\"USERNAME\",\"password\":\"PASSWORD\",\"admin\":false,\"mac\":\"$MAC\"}"

# Create registration token
curl -X POST "$HS/_synapse/admin/v1/registration_tokens/new" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"uses_allowed":5,"token":"my-token"}'

# Invite federated user
curl -X POST "$HS/_matrix/client/v3/rooms/ROOM_ID/invite" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"user_id":"@user:matrix.org"}'
```
