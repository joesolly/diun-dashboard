import json
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_PATH         = os.environ.get("DB_PATH", "/data/diun.db")
PORTAINER_URL   = os.environ.get("PORTAINER_URL", "").rstrip("/")
PORTAINER_TOKEN = os.environ.get("PORTAINER_TOKEN", "")


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con

def init_db():
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS updates (
                image         TEXT PRIMARY KEY,
                status        TEXT,
                hostname      TEXT,
                digest        TEXT,
                hub_link      TEXT,
                platform      TEXT,
                image_created TEXT,
                first_seen    TEXT,
                last_seen     TEXT,
                seen_count    INTEGER NOT NULL DEFAULT 1
            )
        """)

def row_to_dict(row):
    d = dict(row)
    try:
        d["platform"] = json.loads(d["platform"] or "{}")
    except (ValueError, TypeError):
        d["platform"] = {}
    return d


# ── Portainer helper ──────────────────────────────────────────────────────────

def portainer_req(method, path, body=None):
    if not PORTAINER_URL or not PORTAINER_TOKEN:
        return None, "Portainer not configured (set PORTAINER_URL and PORTAINER_TOKEN)"
    url  = f"{PORTAINER_URL}/api{path}"
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", PORTAINER_TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or "{}"), None
    except urllib.error.HTTPError as e:
        return None, f"Portainer HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return None, str(e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}

    image    = payload.get("image", "unknown")
    status   = payload.get("status", "unknown")
    hostname = payload.get("hostname", "unknown")
    digest   = payload.get("digest", "")
    hub_link = payload.get("hub_link", "")
    platform = json.dumps(payload.get("platform") or {})
    created  = payload.get("created", "")
    now      = datetime.now(timezone.utc).isoformat()

    with get_db() as con:
        con.execute("""
            INSERT INTO updates
                (image, status, hostname, digest, hub_link, platform,
                 image_created, first_seen, last_seen, seen_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(image) DO UPDATE SET
                status        = excluded.status,
                hostname      = excluded.hostname,
                digest        = excluded.digest,
                hub_link      = excluded.hub_link,
                platform      = excluded.platform,
                image_created = excluded.image_created,
                last_seen     = excluded.last_seen,
                seen_count    = seen_count + 1
        """, (image, status, hostname, digest, hub_link, platform,
              created, now, now))

    return jsonify({"ok": True}), 200


@app.route("/api/updates")
def api_updates():
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM updates ORDER BY last_seen DESC"
        ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/clear", methods=["POST"])
def clear():
    body  = request.get_json(silent=True, force=True) or {}
    image = body.get("image")
    with get_db() as con:
        if image:
            con.execute("DELETE FROM updates WHERE image = ?", (image,))
        else:
            con.execute("DELETE FROM updates")
    return jsonify({"ok": True})


@app.route("/api/config")
def api_config():
    return jsonify({"portainer": bool(PORTAINER_URL and PORTAINER_TOKEN)})


@app.route("/api/portainer/stacks")
def api_portainer_stacks():
    data, err = portainer_req("GET", "/stacks")
    if err:
        return jsonify({"error": err}), 502
    stacks = [
        {"id": s["Id"], "name": s["Name"], "endpointId": s["EndpointId"]}
        for s in (data or [])
    ]
    return jsonify(stacks)


@app.route("/api/portainer/redeploy", methods=["POST"])
def api_portainer_redeploy():
    body        = request.get_json(silent=True) or {}
    stack_id    = body.get("stackId")
    endpoint_id = body.get("endpointId")
    if not stack_id or not endpoint_id:
        return jsonify({"error": "stackId and endpointId are required"}), 400
    _, err = portainer_req(
        "POST", f"/stacks/{stack_id}/redeploy",
        {"endpointId": endpoint_id, "pullImage": True}
    )
    if err:
        return jsonify({"error": err}), 502
    return jsonify({"ok": True})


@app.route("/")
def index():
    return render_template("index.html")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
