"""Local-only ARIADNE control surface and feed interface."""
from __future__ import annotations

import base64
import json
import os
import secrets
import signal
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import ariadne
from .acquisition import MAX_BYTES
from .dashboard import PAGE, progress_summary, submit_manifest
from .store import encoded, event, identity
from .storage import (
    cleanup,
    ensure_upload_capacity,
    evict_source,
    list_sources,
    load_policy,
    save_policy,
    set_pin,
    usage,
)


def accept_message(con, root, message_id, stream, content):
    if not all(isinstance(x, str) and x for x in (message_id, stream, content)):
        raise ValueError("message_id, stream and content are required strings")
    con.execute("INSERT OR IGNORE INTO chat_messages VALUES(?,?,?)", (message_id, stream, content))
    used = {
        m
        for row in con.execute("SELECT message_ids FROM chat_checkpoints WHERE stream=?", (stream,))
        for m in json.loads(row[0])
    }
    pending = [
        dict(r)
        for r in con.execute("SELECT * FROM chat_messages WHERE stream=? ORDER BY rowid", (stream,))
        if r["message_id"] not in used
    ]
    count = 0
    while len(pending) >= 20:
        group, pending = pending[:20], pending[20:]
        ids = [m["message_id"] for m in group]
        cid = identity("CHECKPOINT", stream, ids)
        path = Path(root) / "inbox" / (cid + ".json")
        path.write_text(encoded(dict(lane="G0", messages=group)), encoding="utf-8")
        sid, _, _ = ariadne.register_source(path, connection=con, move_into_custody=True)
        con.execute("INSERT OR IGNORE INTO chat_checkpoints VALUES(?,?,?,?)", (cid, stream, encoded(ids), sid))
        event(con, "G0_CHECKPOINT", cid, dict(source_id=sid, message_ids=ids))
        count += 1
    return dict(checkpoints_created=count, pending_messages=len(pending))


def _queue_rows(con, limit=100):
    rows = []
    for r in con.execute(
        """SELECT job_id,url,status,attempts,depth,detail
           FROM acquisition_jobs
           WHERE status IN ('QUEUED','FETCH_FAILED','STORAGE_DEFERRED','AUTH_REQUIRED',
                            'PAYWALLED','ROBOTS_BLOCKED','BANKED_DEPTH')
           ORDER BY CASE status
             WHEN 'QUEUED' THEN 0
             WHEN 'FETCH_FAILED' THEN 1
             WHEN 'STORAGE_DEFERRED' THEN 2
             ELSE 3 END,
             depth,job_id LIMIT ?""",
        (int(limit),),
    ):
        item = dict(r)
        try:
            detail = json.loads(item["detail"] or "{}")
        except (ValueError, TypeError):
            detail = {}
        item["reason"] = detail.get("reason") or detail.get("error") or ""
        rows.append(item)
    return rows


def serve(port=8765, interval=10, stop_file=None):
    from warden import watch

    if not 1 <= port <= 65535 or interval <= 0:
        raise ValueError("invalid port or interval")

    stop = threading.Event()
    pause = threading.Event()
    downloads_pause = threading.Event()
    mutex = threading.RLock()
    token = secrets.token_urlsafe(32)

    stop_path = Path(stop_file).resolve() if stop_file else None
    if stop_path:
        stop_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            stop_path.unlink()
        except FileNotFoundError:
            pass

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, mime="application/json"):
            data = data.encode() if isinstance(data, str) else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def json_body(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 36 * 1024 * 1024:
                raise ValueError("request size out of bounds")
            return json.loads(self.rfile.read(size))

        def do_GET(self):
            if not self.allowed():
                self.send(403, "{}")
                return

            path = urlsplit(self.path).path

            if path == "/":
                self.send(200, PAGE.replace("__TOKEN__", token), "text/html; charset=utf-8")
                return

            if path == "/api/health":
                self.send(
                    200,
                    encoded(
                        dict(
                            service="ARIADNE",
                            status="ok",
                            pid=os.getpid(),
                            root=str(ariadne.ROOT.resolve()),
                            paused=pause.is_set(),
                            downloads_paused=downloads_pause.is_set(),
                        )
                    ),
                )
                return

            if path == "/api/status":
                with mutex, ariadne.connect() as con:
                    progress = progress_summary(con)
                    metrics = {}
                    for table, label in (
                        ("sources", "Sources"),
                        ("graph_edges", "Typed relations"),
                        ("active_findings", "Current evidence candidates"),
                        ("branches", "Retained searches"),
                    ):
                        metrics[label] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for row in con.execute("SELECT status,COUNT(*) FROM acquisition_jobs GROUP BY status"):
                        metrics["Acquisition " + row[0]] = row[1]
                    for row in con.execute("SELECT lane,COUNT(*) FROM source_lanes GROUP BY lane"):
                        metrics[row[0]] = row[1]
                    metrics["Unextracted sources"] = con.execute(
                        "SELECT COUNT(*) FROM sources WHERE text_extracted=0"
                    ).fetchone()[0]
                    metrics["Reignited torches"] = con.execute(
                        "SELECT COUNT(*) FROM torches WHERE state='REIGNITED'"
                    ).fetchone()[0]
                    storage_state = usage(ariadne.ROOT, con=con, include_venv=False)
                    sources = list_sources(con, ariadne.ROOT, 100)
                    queue = _queue_rows(con, 100)
                    last_event = con.execute(
                        "SELECT seq,stage,subject,created FROM pipeline_events ORDER BY seq DESC LIMIT 1"
                    ).fetchone()
                    activity = dict(last_event) if last_event else None

                health = ariadne.ARTIFACTS_DIR / "watch_status.json"
                try:
                    worker = json.loads(health.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    worker = dict(status="STARTING")

                worker["paused"] = pause.is_set()
                worker["downloads_paused"] = downloads_pause.is_set()
                if pause.is_set():
                    worker["status"] = "PAUSED"

                self.send(
                    200,
                    encoded(
                        dict(
                            worker=worker,
                            metrics=metrics,
                            progress=progress,
                            storage=storage_state,
                            storage_policy=load_policy(ariadne.ROOT),
                            sources=sources,
                            queue=queue,
                            activity=activity,
                        )
                    ),
                )
                return

            if path in ("/report", "/pipeline_state.json", "/neurite_notes.md"):
                name = {"/report": "latest_report.html"}.get(path, path.lstrip("/"))
                file = ariadne.ARTIFACTS_DIR / name
                if file.exists():
                    self.send(
                        200,
                        file.read_bytes(),
                        "text/html; charset=utf-8" if path == "/report" else "text/plain; charset=utf-8",
                    )
                else:
                    self.send(200, "The first report will appear after the next processing cycle.", "text/plain")
                return

            if path.startswith("/custody/"):
                from urllib.parse import unquote

                file = (ariadne.ROOT / unquote(path.lstrip("/"))).resolve()
                if file.is_relative_to(ariadne.CUSTODY_DIR.resolve()) and file.is_file():
                    self.send(200, file.read_bytes(), "application/octet-stream")
                else:
                    self.send(404, "{}")
                return

            self.send(404, "{}")

        def do_POST(self):
            if not self.allowed() or self.headers.get("X-ARIADNE-Token") != token:
                self.send(403, "{}")
                return

            try:
                body = self.json_body()

                # Runtime controls do not need the SQLite writer lock unless they
                # also mutate persisted queue state.
                if self.path == "/api/control":
                    action = body.get("action")
                    if action == "pause":
                        pause.set()
                        result = {"status": "PAUSED"}
                    elif action == "resume":
                        pause.clear()
                        result = {"status": "RUNNING"}
                    elif action == "pause_downloads":
                        downloads_pause.set()
                        result = {"downloads_paused": True}
                    elif action == "resume_downloads":
                        downloads_pause.clear()
                        with mutex, ariadne.connect() as con:
                            con.execute(
                                "UPDATE acquisition_jobs SET status='QUEUED' WHERE status='STORAGE_DEFERRED'"
                            )
                        result = {"downloads_paused": False}
                    elif action == "stop":
                        stop.set()
                        result = {"status": "STOPPING"}
                    else:
                        raise ValueError("unknown control action")
                    self.send(200, encoded(result))
                    return

                with mutex, ariadne.connect() as con:
                    if self.path == "/api/acquire":
                        raw = body["text"]
                        if not isinstance(raw, str):
                            raise ValueError("text must be a string")
                        result = submit_manifest(con, raw)

                    elif self.path == "/api/upload":
                        data = base64.b64decode(body["data"], validate=True)
                        if len(data) > MAX_BYTES:
                            raise ValueError("upload exceeds 25 MiB")
                        ensure_upload_capacity(ariadne.ROOT, len(data), con=con)
                        name = Path(body["name"].replace("\\", "/")).name
                        if not name or name in (".", ".."):
                            raise ValueError("invalid file name")
                        target = ariadne.INBOX_DIR / (
                            ("chat-" if body.get("lane") == "G0" else "")
                            + secrets.token_hex(4)
                            + "-"
                            + name
                        )
                        temporary = target.with_name(target.name + ".part")
                        temporary.write_bytes(data)
                        temporary.replace(target)
                        result = dict(queued=name)

                    elif self.path == "/api/messages":
                        result = accept_message(
                            con,
                            ariadne.ROOT,
                            body["message_id"],
                            body["stream"],
                            body["content"],
                        )

                    elif self.path == "/api/storage/settings":
                        updates = {}
                        if "mode" in body:
                            updates["mode"] = body["mode"]
                        if "local_budget_bytes" in body:
                            updates["local_budget_bytes"] = int(body["local_budget_bytes"])
                        if "free_space_reserve_bytes" in body:
                            updates["free_space_reserve_bytes"] = int(body["free_space_reserve_bytes"])
                        if "auto_evict_g0_originals" in body:
                            updates["auto_evict_g0_originals"] = bool(body["auto_evict_g0_originals"])
                        if "auto_evict_reacquirable_text_originals" in body:
                            updates["auto_evict_reacquirable_text_originals"] = bool(body["auto_evict_reacquirable_text_originals"])
                        result = save_policy(ariadne.ROOT, updates)
                        con.execute(
                            "UPDATE acquisition_jobs SET status='QUEUED' WHERE status='STORAGE_DEFERRED'"
                        )

                    elif self.path == "/api/source":
                        action = body.get("action")
                        source_id = body.get("source_id")
                        if not isinstance(source_id, str) or not source_id:
                            raise ValueError("source_id is required")
                        if action == "pin":
                            set_pin(con, source_id, True)
                            result = {"source_id": source_id, "pinned": True}
                        elif action == "unpin":
                            set_pin(con, source_id, False)
                            result = {"source_id": source_id, "pinned": False}
                        elif action == "evict":
                            result = evict_source(con, ariadne.ROOT, source_id)
                        elif action == "reacquire":
                            changed=con.execute(
                                """UPDATE acquisition_jobs
                                   SET status='QUEUED',attempts=0,next_attempt=0
                                   WHERE source_id=?""",(source_id,)
                            ).rowcount
                            if not changed:
                                raise ValueError("this source has no recorded network acquisition path")
                            result={"source_id":source_id,"status":"QUEUED_FOR_REACQUISITION"}
                        else:
                            raise ValueError("unknown source action")

                    elif self.path == "/api/queue":
                        action = body.get("action")
                        job_id = body.get("job_id")
                        if not isinstance(job_id, str) or not job_id:
                            raise ValueError("job_id is required")
                        if action == "cancel":
                            con.execute(
                                "UPDATE acquisition_jobs SET status='CANCELLED' WHERE job_id=? AND status IN ('QUEUED','FETCH_FAILED','STORAGE_DEFERRED')",
                                (job_id,),
                            )
                            result = {"job_id": job_id, "status": "CANCELLED"}
                        elif action == "retry":
                            con.execute(
                                "UPDATE acquisition_jobs SET status='QUEUED',attempts=0,next_attempt=0 WHERE job_id=?",
                                (job_id,),
                            )
                            result = {"job_id": job_id, "status": "QUEUED"}
                        else:
                            raise ValueError("unknown queue action")

                    elif self.path == "/api/cleanup":
                        result = cleanup(ariadne.ROOT, body.get("kind"))

                    else:
                        self.send(404, "{}")
                        return

                self.send(200, encoded(result))

            except sqlite3.Error as exc:
                self.send(503, encoded(dict(error="Research transaction in progress; retry shortly: " + str(exc))))
            except (ValueError, KeyError, OSError, TypeError) as exc:
                self.send(400, encoded(dict(error=str(exc))))

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 0.5
    worker = threading.Thread(
        target=watch,
        kwargs=dict(
            interval=interval,
            stop_event=stop,
            pause_event=pause,
            acquisition_pause_event=downloads_pause,
            mutex=mutex,
        ),
        daemon=True,
    )

    old = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    worker.start()
    print(f"ARIADNE running at http://127.0.0.1:{port}", flush=True)

    try:
        while not stop.is_set():
            if stop_path and stop_path.exists():
                stop.set()
                break
            server.handle_request()
    finally:
        stop.set()
        worker.join(timeout=60)
        server.server_close()
        if stop_path:
            try:
                stop_path.unlink()
            except FileNotFoundError:
                pass
        for sig, handler in old.items():
            signal.signal(sig, handler)