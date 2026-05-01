# diun-dashboard

A minimal web UI for [DIUN](https://crazymax.dev/diun/) (Docker Image Update Notifier). Receives DIUN webhook events and displays a live dashboard of which images have updates, with one-click Portainer stack redeploys.

![screenshot placeholder](https://via.placeholder.com/800x400?text=diun-dashboard)

## Features

- Receives DIUN webhook payloads and persists them to SQLite (WAL mode, race-safe)
- Filters by status: **new** (first seen) / **update** (digest changed)
- Infers GitHub links from image names (`ghcr.io`, `lscr.io/linuxserver`, `hotio`)
- One-click Portainer stack redeploy with auto stack matching and pull
- Deep-link support (`?image=ghcr.io/hotio/sonarr:latest`) for direct links from notifications
- Served via gunicorn — no dev server file watcher

## Quick start

Deploy DIUN and the dashboard together in one stack. The DIUN config is embedded inline so no extra files are needed on the host.

```yaml
name: diun
services:
  diun:
    container_name: diun
    image: crazymax/diun:latest
    command: serve
    volumes:
      - diun-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    configs:
      - source: diun_config
        target: /etc/diun/diun.yml
    environment:
      - TZ=America/New_York

      # --- Watch settings ---
      - DIUN_WATCH_WORKERS=20
      - DIUN_WATCH_SCHEDULE=0 9 * * *
      - DIUN_WATCH_JITTER=30s
      - DIUN_WATCH_FIRSTCHECKNOTIF=false

      # --- Docker provider ---
      - DIUN_PROVIDERS_DOCKER=true
      - DIUN_PROVIDERS_DOCKER_WATCHBYDEFAULT=true

      # --- Apprise notifications (optional) ---
      - DIUN_NOTIF_APPRISE_ENDPOINT=http://apprise:8000
      - DIUN_NOTIF_APPRISE_TOKEN=your_apprise_tag

      # --- Dashboard webhook ---
      - DIUN_NOTIF_WEBHOOK_ENDPOINT=http://diun-dashboard:8080/webhook
      - DIUN_NOTIF_WEBHOOK_METHOD=POST
    labels:
      - diun.enable=true
    restart: always
    extra_hosts:
      - host.docker.internal:host-gateway
    depends_on:
      - diun-dashboard

  diun-dashboard:
    image: ghcr.io/joesolly/diun-dashboard:latest
    container_name: diun-dashboard
    restart: unless-stopped
    ports:
      - "8585:8080"
    volumes:
      - diun-dashboard-data:/data
    environment:
      - DB_PATH=/data/diun.db
      - PORTAINER_URL=http://portainer:9000
      - PORTAINER_TOKEN=your_portainer_token

volumes:
  diun-data:
  diun-dashboard-data:

configs:
  diun_config:
    content: |
      notif:
        webhook:
          endpoint: "http://diun-dashboard:8080/webhook"
          method: POST
          headers:
            Content-Type: "application/json"

        apprise:
          tmplTitle: |
            {{- if eq .Entry.Status "new" -}}🆕{{- else -}}🔄{{- end }} {{ .Entry.Image.Name }}
          tmplBody: |
            Status:   {{ .Entry.Status }}
            Host:     {{ .Hostname }}
            Platform: {{ .Entry.Image.Platform }}

            View: http://YOUR_DASHBOARD_HOST:8585/?image={{ .Entry.Image.Name }}
```

The `View:` URL in `tmplBody` deep-links directly to the image card in the dashboard.

## Portainer integration

1. In Portainer, go to **User Settings → Access Tokens** and generate a token.
2. Set `PORTAINER_URL` to your Portainer instance (e.g. `http://portainer:9000` if on the same Docker network, or a Tailscale address).
3. Set `PORTAINER_TOKEN` to the generated token.

When configured, each image card shows a **↺ Redeploy** button. Clicking it expands a panel with a stack dropdown — the dashboard attempts to auto-match the stack by name. Confirming calls Portainer's redeploy API with `pullImage: true`.

## Environment variables

| Variable          | Default            | Description                              |
|-------------------|--------------------|------------------------------------------|
| `DB_PATH`         | `/data/diun.db`    | SQLite database path                     |
| `PORTAINER_URL`   | *(unset)*          | Portainer base URL (enables redeploy UI) |
| `PORTAINER_TOKEN` | *(unset)*          | Portainer API token                      |

## API endpoints

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| `POST` | `/webhook`                  | DIUN webhook receiver                |
| `GET`  | `/api/updates`              | All stored image update records      |
| `POST` | `/api/clear`                | Clear one (`{"image": "..."}`) or all|
| `GET`  | `/api/config`               | Returns `{"portainer": true/false}`  |
| `GET`  | `/api/portainer/stacks`     | Proxied Portainer stack list         |
| `POST` | `/api/portainer/redeploy`   | Trigger stack redeploy via Portainer |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DB_PATH=/tmp/diun-dev.db flask --app app run --debug
```

## Publishing a release

Push a semver tag to trigger a versioned image build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will build `linux/amd64` and `linux/arm64` and push:
- `ghcr.io/joesolly/diun-dashboard:latest`
- `ghcr.io/joesolly/diun-dashboard:1.0.0`
- `ghcr.io/joesolly/diun-dashboard:1.0`
- `ghcr.io/joesolly/diun-dashboard:1`
