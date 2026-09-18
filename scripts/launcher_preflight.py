"""One-click launcher preflight for ARIADNE."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, sqlite3, struct, sys, tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VENV=ROOT/'.venv'
DB=ROOT/'db/ariadne.sqlite'
ARTIFACTS=ROOT/'artifacts'
BACKUPS=ARTIFACTS/'launcher-backups'
LOCK=ROOT/'db/warden.lock'
FORBIDDEN=('conda','anaconda','miniconda','miniforge','mambaforge','nvidia','cuda','windowsapps')

def fail(message): raise RuntimeError(message)

def runtime_check():
    version=platform.python_version();minor=f'{sys.version_info.major}.{sys.version_info.minor}'
    if platform.python_implementation()!='CPython':fail(f'Expected CPython, found {platform.python_implementation()}.')
    if minor not in {'3.13','3.11'}:fail(f'Expected CPython 3.13 or 3.11, found {version}.')
    if struct.calcsize('P')*8!=64:fail('ARIADNE requires a 64-bit Python runtime.')
    if Path(sys.prefix).resolve()!=VENV.resolve():fail(f'Launcher is not running inside the repository .venv: {sys.prefix}')
    base=Path(getattr(sys,'_base_executable',sys.executable))
    if any(term in str(base).lower() for term in FORBIDDEN):fail(f'Virtual environment inherits from a rejected Python distribution: {base}')
    cfg=VENV/'pyvenv.cfg'
    if not cfg.is_file():fail('Virtual environment is missing pyvenv.cfg.')
    cfg_text=cfg.read_text(encoding='utf-8',errors='replace').lower()
    if 'include-system-site-packages = false' not in cfg_text:fail('Virtual environment must not inherit global system site-packages.')
    return dict(version=version,implementation=platform.python_implementation(),bits=64,executable=sys.executable,base_executable=str(base),system_site_packages=False)

def sqlite_feature_check():
    with closing(sqlite3.connect(':memory:')) as con:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('CREATE VIRTUAL TABLE fts_probe USING fts5(text)')
        con.execute("INSERT INTO fts_probe VALUES ('ariadne')")
        if con.execute("SELECT COUNT(*) FROM fts_probe WHERE fts_probe MATCH 'ariadne'").fetchone()[0]!=1:fail('SQLite FTS5 probe failed.')
        if con.execute("SELECT json_valid('{\"ok\":true}')").fetchone()[0]!=1:fail('SQLite JSON probe failed.')
    return dict(sqlite_version=sqlite3.sqlite_version,fts5=True,json=True)

def lock_check():
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    with LOCK.open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.seek(0);handle.write(b'0');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError('Another ARIADNE Warden is already running from this repository.') from exc
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:raise RuntimeError('Another ARIADNE Warden is already running from this repository.') from exc
            fcntl.flock(handle,fcntl.LOCK_UN)

def write_check():
    for directory in (ROOT/'db',ROOT/'inbox',ROOT/'custody',ARTIFACTS,ROOT/'config'):
        directory.mkdir(parents=True,exist_ok=True)
        probe=directory/f'.launcher-write-probe-{os.getpid()}';probe.write_text('ok',encoding='utf-8');probe.unlink()
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temp:
        probe_db=Path(temp)/'close-probe.sqlite'
        with closing(sqlite3.connect(probe_db)) as con:
            con.execute('CREATE TABLE probe(value INTEGER)');con.execute('INSERT INTO probe VALUES (1)');con.commit()
        probe_db.unlink()
        if probe_db.exists():fail('SQLite close/delete probe failed; Windows file handle remained open.')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def backup_existing_database():
    if not DB.exists():return None
    if DB.stat().st_size==0:fail(f'Existing database is empty/corrupt: {DB}')
    BACKUPS.mkdir(parents=True,exist_ok=True);temporary=BACKUPS/f'.prestart-{os.getpid()}.sqlite'
    if temporary.exists():temporary.unlink()
    source=sqlite3.connect(DB,timeout=10)
    try:
        source.execute('PRAGMA busy_timeout=10000')
        integrity=source.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':fail(f'Existing ARIADNE database failed integrity_check: {integrity}')
        with closing(sqlite3.connect(temporary)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':fail('Pre-start backup failed SQLite integrity_check.')
    finally:source.close()
    sha=digest(temporary);existing=sorted(BACKUPS.glob(f'prestart-*-{sha[:12]}.sqlite'))
    if existing:temporary.unlink();return str(existing[-1])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');final=BACKUPS/f'prestart-{stamp}-{sha[:12]}.sqlite';temporary.replace(final)
    final.with_suffix('.json').write_text(json.dumps(dict(file=final.name,sha256=sha,source=str(DB.relative_to(ROOT)),created_utc=datetime.now(timezone.utc).isoformat()),indent=2),encoding='utf-8')
    return str(final)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backup',action='store_true');args=parser.parse_args()
    runtime=runtime_check();lock_check();write_check();sqlite_info=sqlite_feature_check();backup=backup_existing_database() if args.backup else None
    print(json.dumps(dict(status='PASS',runtime=runtime,sqlite=sqlite_info,backup=backup,root=str(ROOT)),indent=2));return 0

if __name__=='__main__':raise SystemExit(main())