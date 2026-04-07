# dstack-matrix

Example: Matrix homeserver on Phala Network TEE (dstack).

## What this repo is

A minimal, copy-paste-ready example of running Continuwuity (Matrix homeserver) on a Phala dstack CVM. Public reference for anyone wanting to run Matrix in a TEE.

## What this repo is NOT

This is not the Teleport Router deployment. That lives at `~/projects/teleport/dev-router-matrix/` (private repo `Account-Link/dev-router-matrix`).

## Related repos

| Repo | Visibility | Purpose |
|---|---|---|
| `dstack-matrix` | public | This one -- example/tutorial |
| `Account-Link/dev-router-matrix` | private | Teleport Router product (MCP bot, live CVM) |
| `amiller/hermes-introducer` | public (archived) | Standalone hivemind POC, cross-agent introductions |

## Folder structure

```
docker-compose.yml          — Continuwuity only (minimal example)
continuwuity/
  continuwuity.toml         — server config (edit server_name + reg token)
synapse/                    — archived Synapse deployment (historical reference)
  DEPLOY.md                 — old Synapse deploy docs
  docker-compose.yaml
  Dockerfile
  homeserver.yaml.tmpl
  nginx.conf
  ...
```

## Deploy

```bash
# 1. Edit continuwuity/continuwuity.toml with your app ID and token
# 2. Deploy
phala deploy --cvm-id my-matrix-server -c docker-compose.yml
phala cvms restart <UUID>
# 3. Server at: https://<APP-ID>-6167.dstack-pha-prod7.phala.network
```

## CVM details

- Production CVM: `dstack-continuwuity`
- Gateway: `dstack-pha-prod7.phala.network`
- Port mapping: container 6167 → gateway `<APP-ID>-6167`
- SSH: `phala ssh dstack-continuwuity`
