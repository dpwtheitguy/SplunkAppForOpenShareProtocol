"""OpenSharing table provider for the OpenShare app."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask


def deployment_secret(name):
    file = os.getenv(name + "_FILE")
    value = Path(file).read_text(encoding="utf-8").strip() if file else os.environ[name]
    if len(value) < 32:
        raise ValueError(f"{name} must contain at least 32 characters.")
    return value


root = Path("/data")
root.mkdir(exist_ok=True)
prefix = "/open-sharing"
endpoint = os.environ["ENDPOINT"].rstrip("/")
public_url = urlsplit(endpoint)
if (
    public_url.scheme != "https"
    or not public_url.hostname
    or public_url.path != prefix
    or public_url.username is not None
    or public_url.query
    or public_url.fragment
):
    raise ValueError("ENDPOINT must be an HTTPS URL ending in /open-sharing.")
internal_key = deployment_secret("OPENSHARE_KEY")
file_key = deployment_secret("FILE_KEY").encode()
audit_dir = Path(os.environ.get("AUDIT_EXPORT_DIR", "/audit"))
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    task = asyncio.create_task(audit_export_loop()) if audit_dir.is_dir() else None
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@contextmanager
def db():
    connection = sqlite3.connect(root / "shares.db")
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots(
            id TEXT PRIMARY KEY, owner TEXT, name TEXT, source TEXT, fields TEXT,
            rows INTEGER, created INTEGER, published INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS grants(
            id TEXT PRIMARY KEY, snapshot TEXT, digest TEXT UNIQUE, label TEXT,
            expires INTEGER, revoked INTEGER DEFAULT 0, last_used INTEGER);
        CREATE TABLE IF NOT EXISTS activity(
            ts INTEGER, event TEXT, actor TEXT, snapshot TEXT, grant_id TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value INTEGER);
        INSERT OR IGNORE INTO settings VALUES ('access_audit', 1), ('debug_until', 0);
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(snapshots)")}
        for name, definition in {
            "source_config": "TEXT",
            "replacement_for": "TEXT",
            "active_file": "TEXT",
            "version": "INTEGER DEFAULT 0",
            "base_version": "INTEGER",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {definition}")


def epoch():
    return int(time.time())


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


@app.middleware("http")
async def diagnostic_context(request, call_next):
    request_id = secrets.token_hex(8)
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-OpenShare-Request-ID"] = request_id
    with db() as conn:
        debug_until = conn.execute("SELECT value FROM settings WHERE key='debug_until'").fetchone()[
            0
        ]
    if debug_until > epoch():
        route = getattr(request.scope.get("route"), "path", "unmatched")
        logger.info(
            "request_id=%s method=%s route=%s status=%d duration_ms=%d",
            request_id,
            request.method,
            route,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )
    return response


def audit(conn, event, actor="", snapshot="", grant_id="", access=False):
    if (
        access
        and not conn.execute("SELECT value FROM settings WHERE key='access_audit'").fetchone()[0]
    ):
        return
    conn.execute(
        "INSERT INTO activity VALUES (?,?,?,?,?)", (epoch(), event, actor, snapshot, grant_id)
    )


def export_audit():
    """Mirror committed events to Splunk's monitored lab volume."""
    with db() as conn:
        rows = conn.execute(
            """SELECT rowid AS event_id,* FROM activity
               WHERE rowid > COALESCE((SELECT value FROM settings WHERE key='audit_cursor'), 0)
               ORDER BY rowid LIMIT 200"""
        ).fetchall()
        for row in rows:
            event = {**dict(row), "timestamp": stamp(row["ts"])}
            date = event["timestamp"][:10]
            with (audit_dir / f"openshare-{date}.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(event) + "\n")
        if rows:
            conn.execute(
                "INSERT OR REPLACE INTO settings VALUES ('audit_cursor', ?)",
                (rows[-1]["event_id"],),
            )


async def audit_export_loop():
    while True:
        try:
            await asyncio.to_thread(export_audit)
        except (OSError, sqlite3.Error) as error:
            logger.warning("audit_mirror_failed error_type=%s", type(error).__name__)
        await asyncio.sleep(2)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def sign(file_id, grant, expires):
    return hmac.digest(file_key, f"{file_id}/{grant}/{expires}".encode(), "sha256").hex()


def owned(conn, snapshot, actor, admin):
    row = conn.execute("SELECT * FROM snapshots WHERE id=?", (snapshot,)).fetchone()
    if not row or (not admin and row["owner"] != actor):
        raise HTTPException(404, "Share was not found")
    return row


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/private/manage")
async def manage(request: Request):
    if not hmac.compare_digest(request.headers.get("x-openshare-key", ""), internal_key):
        raise HTTPException(401)
    data = await request.json()
    return manage_action(data)


def manage_action(data):
    action, actor, admin = data["action"], data["actor"], data["admin"]
    snapshot = data.get("snapshot", "")
    with db() as conn:
        if action != "list":
            conn.execute("BEGIN IMMEDIATE")
        if action == "list":
            shares = conn.execute(
                """SELECT id,owner,name,source,fields,rows,created,published,
                          source_config IS NOT NULL AS can_refresh FROM snapshots
                   WHERE published=1 AND (owner=? OR ?) ORDER BY created DESC""",
                (actor, admin),
            )
            grants = conn.execute(
                """SELECT g.id,g.snapshot,g.label,g.expires,g.revoked,g.last_used,s.name
                   FROM grants g JOIN snapshots s ON g.snapshot=s.id
                   WHERE s.owner=? OR ? ORDER BY g.rowid DESC""",
                (actor, admin),
            )
            events = conn.execute(
                """SELECT a.* FROM activity a LEFT JOIN snapshots s ON a.snapshot=s.id
                   WHERE s.owner=? OR ? ORDER BY a.rowid DESC LIMIT 100""",
                (actor, admin),
            )
            settings = dict(
                conn.execute("SELECT key,value FROM settings WHERE key!='audit_cursor'")
            )
            return {
                "shares": [dict(row) for row in shares],
                "grants": [dict(row) for row in grants],
                "activity": [dict(row) for row in events],
                "settings": settings,
                "endpoint": endpoint,
            }
        if action == "logging":
            if not admin:
                raise HTTPException(403)
            conn.executemany(
                "UPDATE settings SET value=? WHERE key=?",
                [
                    (int(data["access_audit"]), "access_audit"),
                    (epoch() + 1800 if data["verbose"] else 0, "debug_until"),
                ],
            )
            audit(
                conn,
                "recipient_audit_enabled" if data["access_audit"] else "recipient_audit_disabled",
                actor,
            )
            audit(
                conn,
                "verbose_diagnostics_enabled"
                if data["verbose"]
                else "verbose_diagnostics_disabled",
                actor,
            )
            return {"ok": True}
        if action == "stage":
            return stage(conn, data)
        row = owned(conn, snapshot, actor, admin)
        if action == "refresh_source":
            if not row["published"] or not row["source_config"]:
                raise HTTPException(409, "This share has no refresh configuration")
            return {
                **json.loads(row["source_config"]),
                "name": row["name"],
                "fields": json.loads(row["fields"]),
                "base_version": row["version"],
            }
        if action == "publish":
            if row["replacement_for"]:
                original = owned(conn, row["replacement_for"], actor, admin)
                if not original["published"] or original["version"] != row["base_version"]:
                    raise HTTPException(409, "Share changed since preview. Prepare a new snapshot.")
                conn.execute(
                    """UPDATE snapshots SET active_file=?,version=version+1,rows=?,created=?
                       WHERE id=?""",
                    (snapshot, row["rows"], row["created"], original["id"]),
                )
                audit(conn, "share_refreshed", actor, original["id"])
                return {"ok": True}
            conn.execute("UPDATE snapshots SET published=1 WHERE id=? AND published=0", (snapshot,))
            if not row["published"]:
                audit(conn, "share_published", actor, snapshot)
            return {"ok": True}
        if action == "disable":
            conn.execute("UPDATE snapshots SET published=0 WHERE id=?", (snapshot,))
            conn.execute("UPDATE grants SET revoked=1 WHERE snapshot=?", (snapshot,))
            audit(conn, "share_disabled", actor, snapshot)
            return {"ok": True}
        if action in ("issue", "rotate", "revoke"):
            return change_grant(conn, action, row, data)
        raise HTTPException(400, "Unknown action")


def stage(conn, data):
    fields, rows = data["fields"], data["rows"]
    if (
        not fields
        or len(fields) != len(set(fields))
        or len(rows) > 50000
        or len(json.dumps(rows).encode()) > 100_000_000
    ):
        raise HTTPException(400, "Invalid or oversized snapshot")
    snapshot = secrets.token_hex(16)
    table = pa.table(
        {field: pa.array([row.get(field) for row in rows], type=pa.string()) for field in fields}
    )
    file = root / f"{snapshot}.parquet"
    pq.write_table(table, file)
    source = {
        key: data.get(key) for key in ("sourceType", "source", "reportOwner", "app", "window")
    }
    conn.execute(
        """INSERT INTO snapshots (id,owner,name,source,fields,rows,created,source_config,
                                  replacement_for,active_file,base_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            snapshot,
            data["actor"],
            data["name"],
            data["source"],
            json.dumps(fields),
            len(rows),
            epoch(),
            json.dumps(source),
            data.get("replacement_for"),
            snapshot,
            data.get("base_version"),
        ),
    )
    if conn.execute("SELECT value FROM settings WHERE key='debug_until'").fetchone()[0] > epoch():
        logger.info("snapshot_materialized snapshot=%s rows=%d", snapshot, len(rows))
    return {
        "id": snapshot,
        "name": data["name"],
        "rows": len(rows),
        "fields": fields,
        "sample": [{field: row.get(field) for field in fields} for row in rows[:10]],
    }


def change_grant(conn, action, row, data):
    actor, snapshot = data["actor"], row["id"]
    previous = None
    if action in ("rotate", "revoke"):
        previous = conn.execute(
            "SELECT * FROM grants WHERE id=? AND snapshot=? AND revoked=0",
            (data.get("grant"), snapshot),
        ).fetchone()
        if not previous:
            raise HTTPException(404, "Active grant was not found")
        conn.execute("UPDATE grants SET revoked=1 WHERE id=?", (previous["id"],))
        if action == "revoke":
            audit(conn, "grant_revoked", actor, snapshot, previous["id"])
            return {"ok": True}
    if not row["published"]:
        raise HTTPException(409, "Publish the snapshot before issuing access")
    days = int(data.get("days", 7))
    if not 1 <= days <= 30:
        raise HTTPException(400, "Choose an expiration between 1 and 30 days")
    label = previous["label"] if previous else str(data.get("label", "")).strip()
    if not label or len(label) > 100:
        raise HTTPException(400, "Enter a recipient label of up to 100 characters")
    verifier = data["verifier"]
    if not re.fullmatch(r"[a-f0-9]{64}", verifier):
        raise HTTPException(400, "Invalid verifier")
    grant = secrets.token_hex(16)
    expires = epoch() + days * 86400
    conn.execute(
        "INSERT INTO grants VALUES (?,?,?,?,?,0,NULL)", (grant, snapshot, verifier, label, expires)
    )
    audit(conn, f"grant_{'rotated' if previous else 'issued'}", actor, snapshot, grant)
    return {"endpoint": endpoint, "expirationTime": stamp(expires), "shareCredentialsVersion": 1}


def authorized(request, share=None, schema=None, table=None):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    with db() as conn:
        row = (
            conn.execute(
                """SELECT s.*,g.id AS grant_id,g.expires,g.revoked FROM grants g
               JOIN snapshots s ON s.id=g.snapshot WHERE g.digest=?""",
                (digest(token),),
            ).fetchone()
            if scheme.lower() == "bearer" and token
            else None
        )
        if not row or not row["published"] or row["revoked"] or row["expires"] <= epoch():
            audit(
                conn,
                "recipient_denied",
                snapshot=row["id"] if row else "",
                grant_id=row["grant_id"] if row else "",
                access=True,
            )
            result = 401
        elif (
            (share is not None and share != row["id"])
            or (schema is not None and schema != "data")
            or (table is not None and table != "snapshot")
        ):
            audit(
                conn, "recipient_denied", snapshot=row["id"], grant_id=row["grant_id"], access=True
            )
            result = 404
        else:
            return row
    raise HTTPException(result)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    if request.url.path.startswith(prefix):
        return JSONResponse(
            {
                "errorCode": {
                    401: "UNAUTHENTICATED",
                    404: "RESOURCE_DOES_NOT_EXIST",
                    400: "INVALID_PARAMETER_VALUE",
                }.get(exc.status_code, "ERROR"),
                "message": str(exc.detail),
            },
            status_code=exc.status_code,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get(prefix + "/shares")
def shares(request: Request):
    row = authorized(request)
    return {"items": [{"name": row["id"]}]}


@app.get(prefix + "/shares/{share}")
def share_info(request: Request, share: str):
    authorized(request, share)
    return {"share": {"name": share}}


@app.get(prefix + "/shares/{share}/schemas")
def schemas(request: Request, share: str):
    authorized(request, share)
    return {"items": [{"name": "data", "share": share}]}


table_path = prefix + "/shares/{share}/schemas/{schema}/tables/{table}"


@app.get(prefix + "/shares/{share}/all-tables")
@app.get(prefix + "/shares/{share}/schemas/{schema}/tables")
def tables(request: Request, share: str, schema: str = "data"):
    authorized(request, share, schema)
    return {
        "items": [{"name": "snapshot", "share": share, "schema": schema, "accessModes": ["url"]}]
    }


@app.get(table_path)
def table_info(request: Request, share: str, schema: str, table: str):
    authorized(request, share, schema, table)
    return {"name": table, "share": share, "schema": schema, "format": "delta"}


@app.get(table_path + "/version")
@app.head(table_path)
def version(request: Request, share: str, schema: str, table: str):
    row = authorized(request, share, schema, table)
    return Response(headers={"Delta-Table-Version": str(row["version"])})


def metadata(row):
    fields = [
        {"name": name, "type": "string", "nullable": True, "metadata": {}}
        for name in json.loads(row["fields"])
    ]
    return [
        {"protocol": {"minReaderVersion": 1}},
        {
            "metaData": {
                "id": row["id"],
                "format": {"provider": "parquet"},
                "schemaString": json.dumps({"type": "struct", "fields": fields}),
                "partitionColumns": [],
            }
        },
    ]


def ndjson(items, version):
    return Response(
        "".join(json.dumps(item) + "\n" for item in items),
        media_type="application/x-ndjson",
        headers={"Delta-Table-Version": str(version)},
    )


@app.get(table_path + "/metadata")
def table_metadata(request: Request, share: str, schema: str, table: str):
    row = authorized(request, share, schema, table)
    return ndjson(metadata(row), row["version"])


@app.post(table_path + "/query")
async def query(request: Request, share: str, schema: str, table: str):
    row = authorized(request, share, schema, table)
    options = await request.json()
    if (
        options.get("version", row["version"]) != row["version"]
        or options.get("timestamp")
        or "startingVersion" in options
    ):
        raise HTTPException(400, "Only the latest snapshot is available")
    expires = min(epoch() + 300, row["expires"])
    grant = row["grant_id"]
    file_id = row["active_file"] or share
    url = f"{endpoint}/files/{file_id}/{grant}/{expires}/{sign(file_id, grant, expires)}"
    file = root / f"{file_id}.parquet"
    with db() as conn:
        conn.execute("UPDATE grants SET last_used=? WHERE id=?", (epoch(), row["grant_id"]))
        audit(conn, "snapshot_requested", snapshot=share, grant_id=row["grant_id"], access=True)
    return ndjson(
        metadata(row)
        + [
            {
                "file": {
                    "url": url,
                    "id": file_id,
                    "partitionValues": {},
                    "size": file.stat().st_size,
                }
            }
        ],
        row["version"],
    )


def record_file(grant):
    with db() as conn:
        row = conn.execute("SELECT snapshot FROM grants WHERE id=?", (grant,)).fetchone()
        if row:
            audit(conn, "file_served", snapshot=row["snapshot"], grant_id=grant, access=True)


@app.api_route(prefix + "/files/{snapshot}/{grant}/{expires}/{signature}", methods=["GET", "HEAD"])
def download(snapshot: str, grant: str, expires: int, signature: str, request: Request):
    if (
        not re.fullmatch(r"[a-f0-9]{32}", snapshot)
        or expires <= epoch()
        or not hmac.compare_digest(signature, sign(snapshot, grant, expires))
    ):
        raise HTTPException(404)
    event = BackgroundTask(record_file, grant) if request.method == "GET" else None
    return FileResponse(
        root / f"{snapshot}.parquet",
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
        background=event,
    )
