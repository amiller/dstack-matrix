# dstack-matrix

Example deployment of a Matrix homeserver on Phala Network TEE (Trusted Execution Environment) using dstack.

## What's here

```
docker-compose.yml          — Continuwuity homeserver (minimal, ready to deploy)
continuwuity/
  continuwuity.toml         — server config (edit server_name and registration_token)
synapse/                    — archived Synapse deployment (previous iteration)
```

## Quick start

### 1. Edit the config

Replace `your-app-id-6167.dstack-pha-prod7.phala.network` in `continuwuity/continuwuity.toml` with your actual gateway URL (you'll get this after deploying).

Set a registration token so people can create accounts:
```toml
registration_token = "your-secret-token"
```

### 2. Deploy to Phala CVM

```bash
# Create a new CVM
phala cvms create --name my-matrix-server ...

# Deploy the compose file
phala deploy --cvm-id my-matrix-server -c docker-compose.yml

# Restart to apply
phala cvms restart <UUID>
```

### 3. Get your server URL

```bash
phala cvms list
# Look for the app ID, your server is at:
# https://<APP-ID>-6167.dstack-pha-prod7.phala.network
```

### 4. Update config and redeploy

Edit `continuwuity.toml` with the real `server_name`, then:

```bash
phala deploy --cvm-id my-matrix-server -c docker-compose.yml
phala cvms restart <UUID>
```

### 5. Connect

Open Element (or any Matrix client) and point it at your server URL. Register with the token you set.

## Federation

Federation with other homeservers (matrix.org, etc.) works out of the box. Your server is accessible via the Phala gateway with TLS termination.

## Pitfalls we learned

- **Deploy doesn't restart containers** — always follow `phala deploy` with `phala cvms restart <uuid>`
- **Server name must match the gateway URL** — otherwise federation breaks
- **Port 6167** — Phala gateway maps `<APP-ID>-6167.<gateway>` to your container's port 6167
- **Named volumes persist** across restarts — your data survives redeployments
- **Don't delete and recreate the CVM** — you'll get a new app ID and all URLs change

## Why Continuwuity?

Continuwuity (formerly Conduwuit) is a lightweight Matrix homeserver written in Rust. It uses RocksDB, has minimal resource requirements, and works well inside TEE environments where memory and disk are limited.

We previously ran Synapse (Python) — see `synapse/` for the archived deployment. Synapse worked but was heavier and the Docker image was ~1GB vs Continuwuity's ~50MB.
