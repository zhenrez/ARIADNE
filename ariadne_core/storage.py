"""Disk-budgeted storage policy and source-retention controls for ARIADNE."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_POLICY = {
    "mode": "metadata_first",
    "local_budget_bytes": 1024 * 1024 * 1024,
    "free_space_reserve_bytes": 5 * 1024 * 1024 * 1024,
    "metadata_fetch_limit_bytes": 2 * 1024 * 1024,
    "selective_fetch_limit_bytes": 10 * 1024 * 1024,
    "max_source_bytes": 25 * 1024 * 1024,
    "launcher_backup_retention": 2,
    "snapshot_retention": 1,
    "processing_overhead_factor": 3,
    "auto_evict_g0_originals": True,
    "auto_evict_reacquirable_text_originals": True,
}

VALID_MODES = {"metadata_first", "selective", "full"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_storage (
 source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
 state TEXT NOT NULL CHECK(state IN ('PRESENT','EVICTED','MISSING')),
 pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
 reacquirable INTEGER NOT NULL DEFAULT 0 CHECK(reacquirable IN (0,1)),
 updated_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def install(con):
    con.executescript(SCHEMA)


def policy_path(root):
    return Path(root) / "config" / "storage.json"


def validate_policy(data):
    out = dict(DEFAULT_POLICY)
    if isinstance(data, dict):
        out.update(data)
    if out["mode"] not in VALID_MODES:
        raise ValueError("storage mode must be metadata_first, selective, or full")
    for key in (
        "local_budget_bytes", "free_space_reserve_bytes", "metadata_fetch_limit_bytes",
        "selective_fetch_limit_bytes", "max_source_bytes", "launcher_backup_retention",
        "snapshot_retention", "processing_overhead_factor",
    ):
        if type(out[key]) is not int or out[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if type(out["auto_evict_g0_originals"]) is not bool:
        raise ValueError("auto_evict_g0_originals must be boolean")
    if type(out["auto_evict_reacquirable_text_originals"]) is not bool:
        raise ValueError("auto_evict_reacquirable_text_originals must be boolean")
    return out


def load_policy(root):
    path = policy_path(root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save_policy(root, DEFAULT_POLICY)
        return dict(DEFAULT_POLICY)
    try:
        return validate_policy(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return dict(DEFAULT_POLICY)


def save_policy(root, updates):
    current = dict(DEFAULT_POLICY)
    path = policy_path(root)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                current.update(existing)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    current.update(updates or {})
    current = validate_policy(current)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return current


def _tree_bytes(path):
    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def usage(root, con=None, include_venv=True):
    root = Path(root)
    if con is not None:
        try:
            custody = con.execute(
                """SELECT COALESCE(SUM(s.byte_size),0)
                   FROM sources s JOIN source_storage ss USING(source_id)
                   WHERE ss.state='PRESENT'"""
            ).fetchone()[0]
        except Exception:
            custody = _tree_bytes(root / "custody")
    else:
        custody = _tree_bytes(root / "custody")
    categories = {
        "database": _tree_bytes(root / "db"),
        "custody": int(custody or 0),
        "inbox": _tree_bytes(root / "inbox"),
        "artifacts": _tree_bytes(root / "artifacts"),
        "venv": _tree_bytes(root / ".venv") if include_venv else 0,
    }
    research_bytes = sum(categories[k] for k in ("database", "custody", "inbox", "artifacts"))
    disk = shutil.disk_usage(root)
    policy = load_policy(root)
    budget_remaining = max(0, policy["local_budget_bytes"] - research_bytes)
    free_after_reserve = max(0, disk.free - policy["free_space_reserve_bytes"])
    headroom = min(budget_remaining, free_after_reserve)
    return {
        "categories": categories,
        "research_bytes": research_bytes,
        "total_ariadne_bytes": research_bytes + categories["venv"],
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "budget_bytes": policy["local_budget_bytes"],
        "reserve_bytes": policy["free_space_reserve_bytes"],
        "headroom_bytes": headroom,
        "mode": policy["mode"],
        "downloads_allowed": headroom > 0,
    }


def acquisition_limit(root, con=None):
    policy = load_policy(root)
    state = usage(root, con=con, include_venv=False)
    if state["headroom_bytes"] <= 0:
        return 0, "storage budget or free-space reserve reached"
    per_source = {
        "metadata_first": policy["metadata_fetch_limit_bytes"],
        "selective": policy["selective_fetch_limit_bytes"],
        "full": policy["max_source_bytes"],
    }[policy["mode"]]
    safe_headroom = state["headroom_bytes"] // max(1, policy["processing_overhead_factor"])
    if safe_headroom <= 0:
        return 0, "storage headroom is insufficient for source plus processing/index overhead"
    return min(per_source, policy["max_source_bytes"], safe_headroom), None


def ensure_upload_capacity(root, byte_count, con=None):
    policy = load_policy(root)
    state = usage(root, con=con, include_venv=False)
    if byte_count < 0:
        raise ValueError("invalid upload size")
    required = byte_count * max(1, policy["processing_overhead_factor"])
    if required > state["headroom_bytes"]:
        raise OSError("ARIADNE storage budget/free-space reserve would be exceeded by this upload plus processing overhead")
    return True


def sync_source_storage(con, root):
    install(con)
    root = Path(root)
    for row in con.execute("SELECT source_id,custody_path FROM sources"):
        present = (root / row["custody_path"]).is_file()
        job = con.execute(
            "SELECT 1 FROM acquisition_jobs WHERE source_id=? AND url IS NOT NULL LIMIT 1",
            (row["source_id"],),
        ).fetchone()
        existing = con.execute("SELECT * FROM source_storage WHERE source_id=?", (row["source_id"],)).fetchone()
        desired_reacquirable = 1 if job else 0
        if existing is None:
            con.execute(
                "INSERT INTO source_storage VALUES(?,?,?,?,?)",
                (row["source_id"], "PRESENT" if present else "MISSING", 0, desired_reacquirable, _now()),
            )
            continue
        new_state = existing["state"]
        if present:
            new_state = "PRESENT"
        elif existing["state"] == "PRESENT":
            new_state = "MISSING"
        new_reacquirable = max(int(existing["reacquirable"]), desired_reacquirable)
        if new_state != existing["state"] or new_reacquirable != int(existing["reacquirable"]):
            con.execute(
                "UPDATE source_storage SET state=?,reacquirable=?,updated_at=? WHERE source_id=?",
                (new_state, new_reacquirable, _now(), row["source_id"]),
            )


def record_present(con, source_id, reacquirable=False):
    install(con)
    con.execute(
        """INSERT INTO source_storage(source_id,state,pinned,reacquirable,updated_at)
           VALUES(?,?,?,?,?)
           ON CONFLICT(source_id) DO UPDATE SET
             state='PRESENT',
             reacquirable=max(source_storage.reacquirable,excluded.reacquirable),
             updated_at=excluded.updated_at""",
        (source_id, "PRESENT", 0, 1 if reacquirable else 0, _now()),
    )


def mark_reacquirable(con, source_id):
    install(con)
    con.execute(
        "UPDATE source_storage SET reacquirable=1,updated_at=? WHERE source_id=?",
        (_now(), source_id),
    )


def set_pin(con, source_id, pinned):
    install(con)
    if not con.execute("SELECT 1 FROM sources WHERE source_id=?", (source_id,)).fetchone():
        raise ValueError("unknown source")
    con.execute(
        "UPDATE source_storage SET pinned=?,updated_at=? WHERE source_id=?",
        (1 if pinned else 0, _now(), source_id),
    )


def evict_source(con, root, source_id):
    install(con)
    row = con.execute(
        """SELECT s.source_id,s.custody_path,COALESCE(ss.pinned,0) pinned,
                  COALESCE(ss.reacquirable,0) reacquirable,
                  COALESCE(l.lane,'E0') lane
           FROM sources s
           LEFT JOIN source_storage ss USING(source_id)
           LEFT JOIN source_lanes l USING(source_id)
           WHERE s.source_id=?""",
        (source_id,),
    ).fetchone()
    if row is None:
        raise ValueError("unknown source")
    if row["pinned"]:
        raise ValueError("source is pinned; unpin before eviction")
    if not row["reacquirable"]:
        raise ValueError("source is not safely reacquirable; ARIADNE will not evict its only original")
    if row["lane"] != "G0" and not con.execute(
        "SELECT 1 FROM source_profiles WHERE source_id=? LIMIT 1",(source_id,)
    ).fetchone():
        raise ValueError("source has not been compiled/indexed yet; ARIADNE will not evict its original")
    path = Path(root) / row["custody_path"]
    if path.exists():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
    con.execute(
        "UPDATE source_storage SET state='EVICTED',updated_at=? WHERE source_id=?",
        (_now(), source_id),
    )
    return {"source_id": source_id, "state": "EVICTED"}


def maybe_evict_processed_original(con, root, source_id):
    """In metadata-first mode, keep searchable text/provenance and release reacquirable originals."""
    policy=load_policy(root)
    if policy["mode"]!="metadata_first" or not policy["auto_evict_reacquirable_text_originals"]:
        return False
    row=con.execute(
        """SELECT COALESCE(ss.pinned,0) pinned,COALESCE(ss.reacquirable,0) reacquirable,
                  COALESCE(ss.state,'MISSING') state,s.text_extracted
           FROM sources s LEFT JOIN source_storage ss USING(source_id)
           WHERE s.source_id=?""",(source_id,)
    ).fetchone()
    if not row or row["state"]!="PRESENT" or row["pinned"] or not row["reacquirable"] or not row["text_extracted"]:
        return False
    if not con.execute("SELECT 1 FROM source_profiles WHERE source_id=? LIMIT 1",(source_id,)).fetchone():
        return False
    evict_source(con,root,source_id)
    return True


def maybe_evict_g0(con, root, source_id):
    policy = load_policy(root)
    if not policy["auto_evict_g0_originals"]:
        return False
    row = con.execute(
        """SELECT COALESCE(l.lane,'E0') lane,COALESCE(ss.pinned,0) pinned,
                  COALESCE(ss.reacquirable,0) reacquirable
           FROM sources s
           LEFT JOIN source_lanes l USING(source_id)
           LEFT JOIN source_storage ss USING(source_id)
           WHERE s.source_id=?""",
        (source_id,),
    ).fetchone()
    if not row or row["lane"] != "G0" or row["pinned"] or not row["reacquirable"]:
        return False
    evict_source(con, root, source_id)
    return True


def list_sources(con, root, limit=200):
    sync_source_storage(con, root)
    rows = []
    for row in con.execute(
        """SELECT s.source_id,s.original_name,s.byte_size,s.custody_path,
                  COALESCE(l.lane,'E0') lane,
                  ss.state,ss.pinned,ss.reacquirable,s.created_at,
                  (SELECT url FROM acquisition_jobs j WHERE j.source_id=s.source_id ORDER BY rowid LIMIT 1) url
           FROM sources s
           LEFT JOIN source_lanes l USING(source_id)
           JOIN source_storage ss USING(source_id)
           ORDER BY s.created_at DESC LIMIT ?""",
        (int(limit),),
    ):
        item = dict(row)
        item["present"] = (Path(root) / item["custody_path"]).is_file()
        rows.append(item)
    return rows


def custody_consistent(con, root):
    sync_source_storage(con, root)
    import ariadne
    for row in con.execute(
        """SELECT s.source_id,s.sha256,s.custody_path,ss.state
           FROM sources s JOIN source_storage ss USING(source_id)"""
    ):
        path = Path(root) / row["custody_path"]
        if row["state"] == "PRESENT":
            if not path.is_file() or ariadne.sha256_file(path) != row["sha256"]:
                return False
        elif row["state"] == "EVICTED":
            if path.exists():
                return False
        elif row["state"] == "MISSING":
            return False
    return True


def cleanup(root, kind):
    root = Path(root)
    policy = load_policy(root)
    removed = 0
    freed = 0

    def remove_file(path):
        nonlocal removed, freed
        try:
            size = path.stat().st_size
            path.unlink()
            removed += 1
            freed += size
        except OSError:
            pass

    if kind == "staging":
        staging = root / "inbox" / ".staging"
        if staging.exists():
            for path in staging.rglob("*"):
                if path.is_file():
                    remove_file(path)
        acquired = root / "inbox" / "acquired"
        if acquired.exists():
            for path in acquired.rglob("*"):
                if path.is_file():
                    remove_file(path)
        inbox = root / "inbox"
        if inbox.exists():
            for path in inbox.rglob("*.part"):
                remove_file(path)
    elif kind == "snapshots":
        files = sorted((root / "artifacts" / "snapshots").glob("state-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True) if (root / "artifacts" / "snapshots").exists() else []
        for path in files[policy["snapshot_retention"]:]:
            remove_file(path)
            manifest = path.with_suffix(".json")
            if manifest.exists():
                remove_file(manifest)
    elif kind == "backups":
        files = sorted((root / "artifacts" / "launcher-backups").glob("prestart-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True) if (root / "artifacts" / "launcher-backups").exists() else []
        for path in files[policy["launcher_backup_retention"]:]:
            remove_file(path)
            manifest = path.with_suffix(".json")
            if manifest.exists():
                remove_file(manifest)
    else:
        raise ValueError("unknown cleanup kind")
    return {"removed_files": removed, "freed_bytes": freed, "kind": kind}