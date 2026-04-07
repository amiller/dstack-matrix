# dstack-matrix

Example deployment of a Matrix homeserver on Phala Network TEE (dstack).

## What this is

A minimal, copy-paste-ready example of running Continuwuity (Matrix homeserver) on a Phala dstack CVM. Public reference for anyone wanting to run Matrix in a TEE.

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

## Pitfalls

- Deploy doesn't restart containers -- always follow `phala deploy` with `phala cvms restart <uuid>`
- Server name must match the gateway URL, otherwise federation breaks
- Port 6167 maps to gateway as `<APP-ID>-6167`
- Named volumes persist across restarts
- Don't delete and recreate the CVM -- you'll get a new app ID and all URLs change

## Why Continuwuity?

Continuwuity (formerly Conduwuit) is a lightweight Matrix homeserver written in Rust. It uses RocksDB, has minimal resource requirements, and works well inside TEE environments where memory and disk are limited. We previously ran Synapse (Python) -- see `synapse/` for the archived deployment.
