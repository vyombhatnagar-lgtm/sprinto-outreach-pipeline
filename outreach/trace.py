"""Trace stores: every step of every domain is written down, so every decision can be audited.

Two backends with the same interface:
  TraceStore (files)  runs/<run_id>/manifest.json, runs/<run_id>/<domain>/NN_<step>.json
  PgTraceStore        Postgres (Neon) tables `runs` and `steps`, used when DATABASE_URL is set
                      (the Vercel deployment has a read-only filesystem)
"""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import STEP_ORDER, StepRecord


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceStore:
    def __init__(self, runs_dir: Path, run_id: Optional[str] = None):
        self.runs_dir = Path(runs_dir)
        self.run_id = run_id or new_run_id()
        self.root = self.runs_dir / self.run_id
        self.location = str(self.root)

    def domain_dir(self, domain: str) -> Path:
        d = self.root / domain
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, domain: str, step: str) -> Path:
        n = STEP_ORDER.index(step) + 1
        return self.domain_dir(domain) / f"{n:02d}_{step}.json"

    def write_manifest(self, domains: List[str], settings_summary: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "manifest.json").write_text(json.dumps({
            "run_id": self.run_id, "created_at": _now(), "domains": domains, "settings": settings_summary,
        }, indent=2))

    def read_manifest(self) -> Optional[Dict[str, Any]]:
        p = self.root / "manifest.json"
        return json.loads(p.read_text()) if p.exists() else None

    def write_step(self, record: StepRecord) -> Path:
        path = self._path(record.domain, record.step)
        path.write_text(record.model_dump_json(indent=2))
        return path

    def read_step(self, domain: str, step: str) -> Optional[StepRecord]:
        path = self._path(domain, step)
        if not path.exists():
            return None
        return StepRecord.model_validate_json(path.read_text())

    def completed_steps(self, domain: str) -> List[str]:
        return [s for s in STEP_ORDER if self._path(domain, s).exists()]

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        out = []
        if not self.runs_dir.exists():
            return out
        for d in sorted((p for p in self.runs_dir.iterdir() if p.is_dir()), reverse=True)[:limit]:
            m = d / "manifest.json"
            if m.exists():
                out.append(json.loads(m.read_text()))
        return out


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        manifest TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS steps (
        run_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        step TEXT NOT NULL,
        idx INTEGER NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (run_id, domain, step)
    )""",
]


class PgTraceStore:
    """Same interface as TraceStore, backed by Postgres. JSON is stored as text so the
    schema stays trivial; records are re-validated through StepRecord on read."""

    placeholder = "%s"

    def __init__(self, connect: Callable[[], Any], run_id: Optional[str] = None):
        self._connect = connect
        self.run_id = run_id or new_run_id()
        self.location = f"postgres runs/{self.run_id}"
        with self._conn() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    @classmethod
    def from_url(cls, url: str, run_id: Optional[str] = None) -> "PgTraceStore":
        import psycopg
        return cls(lambda: psycopg.connect(url, autocommit=True), run_id)

    def _conn(self):
        return _Conn(self._connect(), self.placeholder)

    def domain_dir(self, domain: str) -> None:  # parity with TraceStore; nothing to create
        return None

    def write_manifest(self, domains: List[str], settings_summary: Dict[str, Any]) -> None:
        m = json.dumps({"run_id": self.run_id, "created_at": _now(), "domains": domains,
                        "settings": settings_summary})
        with self._conn() as c:
            c.execute("INSERT INTO runs (run_id, created_at, manifest) VALUES (%s, %s, %s) "
                      "ON CONFLICT (run_id) DO UPDATE SET manifest = EXCLUDED.manifest",
                      (self.run_id, _now(), m))

    def read_manifest(self) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.one("SELECT manifest FROM runs WHERE run_id = %s", (self.run_id,))
        return json.loads(row[0]) if row else None

    def write_step(self, record: StepRecord) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO steps (run_id, domain, step, idx, status, record, updated_at) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                      "ON CONFLICT (run_id, domain, step) DO UPDATE SET status = EXCLUDED.status, "
                      "record = EXCLUDED.record, updated_at = EXCLUDED.updated_at",
                      (record.run_id, record.domain, record.step, STEP_ORDER.index(record.step) + 1,
                       record.status, record.model_dump_json(), _now()))

    def read_step(self, domain: str, step: str) -> Optional[StepRecord]:
        with self._conn() as c:
            row = c.one("SELECT record FROM steps WHERE run_id = %s AND domain = %s AND step = %s",
                        (self.run_id, domain, step))
        return StepRecord.model_validate_json(row[0]) if row else None

    def completed_steps(self, domain: str) -> List[str]:
        with self._conn() as c:
            rows = c.all("SELECT step FROM steps WHERE run_id = %s AND domain = %s ORDER BY idx",
                         (self.run_id, domain))
        return [r[0] for r in rows]

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.all("SELECT manifest FROM runs ORDER BY created_at DESC LIMIT %s", (limit,))
        return [json.loads(r[0]) for r in rows]


class _Conn:
    """Tiny adapter so the same SQL runs on psycopg (%s) and sqlite3 (?) in tests."""

    def __init__(self, conn, placeholder: str):
        self.conn, self.ph = conn, placeholder

    def _sql(self, sql: str) -> str:
        return sql if self.ph == "%s" else sql.replace("%s", self.ph)

    def execute(self, sql: str, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def one(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.execute(sql, params).fetchall()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.conn.commit()
        finally:
            self.conn.close()


def open_store(settings, run_id: Optional[str] = None):
    """Postgres when DATABASE_URL is set (Vercel + Neon), files otherwise (local CLI)."""
    if settings.database_url:
        return PgTraceStore.from_url(settings.database_url, run_id)
    return TraceStore(settings.runs_dir, run_id)
