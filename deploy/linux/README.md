# Open Notebook on Linux (systemd, native SurrealDB)

Run SurrealDB as a **native binary** (no Docker) plus API, background worker, and Next.js production server under **systemd**.

Default ports in the bundled unit files:

| Service    | Port |
|-----------|------|
| SurrealDB | 7610 |
| FastAPI   | 7605 |
| Next.js   | 7600 |

Adjust paths and users before `systemctl enable --now`.

## 1. One-time server preparation

1. Install **Python 3.11+**, **Node.js 18+**, and [uv](https://docs.astral.sh/uv/).
2. Install **SurrealDB** for Linux from [surrealdb.com/install](https://surrealdb.com/install) (or your distro package). Ensure the binary is on `PATH` or set the full path in `surrealdb.service` (e.g. `/usr/local/bin/surreal`).
3. Clone the app to a fixed directory (examples use `/opt/open-notebook`).
4. Create a service user and data directories (example):

   ```bash
   sudo useradd --system --create-home --home-dir /var/lib/open-notebook --shell /usr/sbin/nologin open-notebook || true
   sudo mkdir -p /opt/open-notebook /var/lib/surreal/open-notebook
   sudo chown -R open-notebook:open-notebook /opt/open-notebook /var/lib/surreal/open-notebook
   sudo -u open-notebook git clone <your-repo-url> /opt/open-notebook
   ```

   Alternatively clone as root into `/opt/open-notebook`, then `sudo chown -R open-notebook:open-notebook /opt/open-notebook`.

5. In the repo root:

   ```bash
   cd /opt/open-notebook
   uv sync
   uv pip install python-magic
   ```

6. Build the frontend (standalone output):

   ```bash
   cd /opt/open-notebook/frontend
   npm ci
   npm run build
   cp -r public .next/standalone/
   cp -r .next/static .next/standalone/.next/static
   ```

   The project runs the UI via [`frontend/start-server.js`](../../frontend/start-server.js) from the `frontend/` directory (same layout as a local `npm run build`).

## 2. Environment files

### Application: `/opt/open-notebook/.env`

Copy [`.env.example`](../../.env.example) to `.env` and set at least:

- `OPEN_NOTEBOOK_ENCRYPTION_KEY`
- `SURREAL_URL=ws://127.0.0.1:7610/rpc` (must match SurrealDB bind and credentials)
- `SURREAL_USER` / `SURREAL_PASSWORD` (same username/password as SurrealDB `start` command)
- `API_PORT=7605`
- `API_HOST=0.0.0.0` if the API should listen on all interfaces; use `127.0.0.1` if only localhost (e.g. behind a reverse proxy on the same host)
- `API_RELOAD=false`

See [environment reference](../../docs/5-CONFIGURATION/environment-reference.md) for LDAP, `AUTH_MODE`, and other options.

### SurrealDB: `/etc/surrealdb.env` (root-only permissions)

Create a file **not** tracked in git:

```bash
sudo install -m 600 /dev/stdin /etc/surrealdb.env <<'EOF'
SURREAL_USER=root
SURREAL_PASSWORD=change-me
SURREAL_BIND=127.0.0.1:7610
SURREAL_DATA=/var/lib/surreal/open-notebook
EOF
sudo chown root:root /etc/surrealdb.env
```

Use a strong password. Match `SURREAL_USER` / `SURREAL_PASSWORD` in `/opt/open-notebook/.env`.

Set `SURREAL_BIND=0.0.0.0:7610` only if you need remote TCP access; prefer keeping the DB on localhost and firewalling port **7610** from the public internet.

## 3. Install systemd units

```bash
sudo cp deploy/linux/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Edit each unit if your install path or `uv` location differs (`which uv`).

Enable and start (order: database first, then API and worker, then frontend):

```bash
sudo systemctl enable --now surrealdb.service
sudo systemctl enable --now open-notebook-api.service open-notebook-worker.service
sudo systemctl enable --now open-notebook-frontend.service
```

## 4. Verification

```bash
curl -sS http://127.0.0.1:7610/
curl -sS http://127.0.0.1:7605/docs
```

Open the UI: `http://<host>:7600`

Logs:

```bash
journalctl -u surrealdb -u open-notebook-api -u open-notebook-worker -u open-notebook-frontend -f
```

## 5. Firewall (optional)

Typically expose **7600** (UI), and **7605** only if clients call the API directly. Keep **7610** restricted to `127.0.0.1` or an admin network. Example (`ufw`):

```bash
sudo ufw allow 7600/tcp
# sudo ufw allow 7605/tcp   # only if needed
```

## 6. Updating the application

```bash
cd /opt/open-notebook
git pull
uv sync
cd frontend && npm ci && npm run build && cp -r public .next/standalone/ && cp -r .next/static .next/standalone/.next/static
sudo systemctl restart open-notebook-api open-notebook-worker open-notebook-frontend
```

Restart `surrealdb` only when upgrading the SurrealDB binary or changing `/etc/surrealdb.env`.
