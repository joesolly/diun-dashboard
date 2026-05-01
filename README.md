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

```yaml
# docker-compose.yml
services:
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
      - PORTAINER_TOKEN=your_token_here

volumes:
  diun-dashboard-data:
```

## DIUN configuration

Add this to your `diun.yml` under the `notif:` key. Replace the URLs and tokens for your environment.

```yaml
notif:
  webhook:
    endpoint: "http://diun-dashboard:8585/webhook"
    method: POST
    headers:
      Content-Type: "application/json"

  pushbullet:
    token: "YOUR_PUSHBULLET_TOKEN"
    title: |
      {{- if eq .Entry.Status "new" -}}🆕{{- else -}}🔄{{- end }} {{ .Entry.Image.Name }}
    body: |
      Status:   {{ .Entry.Status }}
      Host:     {{ .Hostname }}
      Platform: {{ .Entry.Image.Platform }}

      View: http://YOUR_DASHBOARD_HOST:8585/?image={{ .Entry.Image.Name }}
```

The `View:` URL deep-links directly to the image card in the dashboard. Opening it scrolls to and highlights the relevant card.

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
