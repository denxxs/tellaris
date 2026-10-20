"""SQLite persistence for runs, events, personas, reactions and calibration."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  status TEXT NOT NULL,
  stage TEXT,
  progress REAL DEFAULT 0,
  title TEXT,
  prompt TEXT NOT NULL,
  parent_id TEXT,
  request TEXT,
  spec TEXT,
  world TEXT,
  research TEXT,
  results TEXT,
  report TEXT,
  usage TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts REAL NOT NULL,
  type TEXT NOT NULL,
  data TEXT,
  PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS personas (
  run_id TEXT NOT NULL,
  id TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS reactions (
  run_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  run INTEGER NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (run_id, persona_id, run)
);
CREATE TABLE IF NOT EXISTS committees (
  run_id TEXT NOT NULL,
  id TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS feed (
  run_id TEXT NOT NULL,
  id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  author TEXT,
  data TEXT NOT NULL,
  PRIMARY KEY (run_id, id)
);
CREATE INDEX IF NOT EXISTS feed_author ON feed(run_id, author);
CREATE TABLE IF NOT EXISTS chats (
  run_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  messages TEXT NOT NULL,
  PRIMARY KEY (run_id, persona_id)
);
CREATE TABLE IF NOT EXISTS calibrations (
  kind TEXT PRIMARY KEY,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtests (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS predictions_run ON predictions(run_id);
CREATE TABLE IF NOT EXISTS interviews (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS interviews_run ON interviews(run_id);
"""

JSON_COLS = {"request", "spec", "world", "research", "results", "report", "usage"}


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        # A fresh lock for the event loop that opens the store; asyncio locks bind to one loop.
        self._lock = asyncio.Lock()
        if self._db is None:
            self._db = await aiosqlite.connect(self.path)
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(SCHEMA)
            await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("store not open")
        return self._db

    async def _exec(self, sql: str, args: tuple = ()) -> None:
        async with self._lock:
            await self.db.execute(sql, args)
            await self.db.commit()

    async def _many(self, sql: str, rows: list[tuple]) -> None:
        if not rows:
            return
        async with self._lock:
            await self.db.executemany(sql, rows)
            await self.db.commit()

    # ---------- runs ----------

    async def create_run(self, run_id: str, prompt: str, request: dict[str, Any], parent_id: str | None) -> None:
        now = time.time()
        await self._exec(
            "INSERT INTO runs (id, created_at, updated_at, status, stage, prompt, parent_id, request, title) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, now, now, "queued", "queued", prompt, parent_id, json.dumps(request), prompt[:80]),
        )

    async def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols, args = [], []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            args.append(json.dumps(v, default=str) if k in JSON_COLS and v is not None else v)
        cols.append("updated_at = ?")
        args.append(time.time())
        args.append(run_id)
        await self._exec(f"UPDATE runs SET {', '.join(cols)} WHERE id = ?", tuple(args))

    @staticmethod
    def _row(row: aiosqlite.Row, full: bool = True) -> dict[str, Any]:
        d = dict(row)
        for k in JSON_COLS:
            if k in d and d[k] is not None:
                d[k] = json.loads(d[k]) if full else None
        return d

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cur:
            row = await cur.fetchone()
        return self._row(row) if row else None

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, created_at, updated_at, status, stage, progress, title, prompt, parent_id, spec, results, error "
            "FROM runs ORDER BY created_at DESC LIMIT ?"
        )
        async with self.db.execute(sql, (limit,)) as cur:
            rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            spec = json.loads(d.pop("spec")) if d.get("spec") else None
            results = json.loads(d.pop("results")) if d.get("results") else None
            d["targets"] = spec.get("targets") if spec else []
            d["subject_kind"] = spec.get("subject_kind") if spec else None
            d["headline"] = results.get("headline") if results else None
            out.append(d)
        return out

    async def delete_run(self, run_id: str) -> None:
        async with self._lock:
            for table in ("events", "personas", "reactions", "committees", "chats", "feed"):
                await self.db.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
            await self.db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            await self.db.commit()

    async def mark_interrupted(self) -> None:
        await self._exec(
            "UPDATE runs SET status = 'failed', error = 'Interrupted: the server restarted during this run.' "
            "WHERE status IN ('queued', 'running')"
        )

    # ---------- events ----------

    async def add_event(self, run_id: str, seq: int, etype: str, data: Any) -> None:
        await self._exec(
            "INSERT INTO events (run_id, seq, ts, type, data) VALUES (?,?,?,?,?)",
            (run_id, seq, time.time(), etype, json.dumps(data, default=str)),
        )

    async def events(self, run_id: str, after: int = -1) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT seq, ts, type, data FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)
        ) as cur:
            rows = await cur.fetchall()
        return [{"seq": r["seq"], "ts": r["ts"], "type": r["type"], "data": json.loads(r["data"])} for r in rows]

    # ---------- personas & reactions ----------

    async def save_personas(self, run_id: str, people: list[dict[str, Any]]) -> None:
        await self._many(
            "INSERT OR REPLACE INTO personas (run_id, id, data) VALUES (?,?,?)",
            [(run_id, p["id"], json.dumps(p)) for p in people],
        )

    async def personas(self, run_id: str) -> list[dict[str, Any]]:
        async with self.db.execute("SELECT data FROM personas WHERE run_id = ? ORDER BY id", (run_id,)) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def persona(self, run_id: str, pid: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT data FROM personas WHERE run_id = ? AND id = ?", (run_id, pid)) as cur:
            row = await cur.fetchone()
        return json.loads(row["data"]) if row else None

    async def save_reactions(self, run_id: str, reactions: list[dict[str, Any]]) -> None:
        await self._many(
            "INSERT OR REPLACE INTO reactions (run_id, persona_id, run, data) VALUES (?,?,?,?)",
            [(run_id, r["persona_id"], r["run"], json.dumps(r)) for r in reactions],
        )

    async def reactions(self, run_id: str, persona_id: str | None = None) -> list[dict[str, Any]]:
        if persona_id:
            sql, args = "SELECT data FROM reactions WHERE run_id = ? AND persona_id = ? ORDER BY run", (run_id, persona_id)
        else:
            sql, args = "SELECT data FROM reactions WHERE run_id = ? ORDER BY persona_id, run", (run_id,)
        async with self.db.execute(sql, args) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def save_committees(self, run_id: str, committees: list[dict[str, Any]]) -> None:
        await self._many(
            "INSERT OR REPLACE INTO committees (run_id, id, data) VALUES (?,?,?)",
            [(run_id, c["id"], json.dumps(c)) for c in committees],
        )

    async def committees(self, run_id: str) -> list[dict[str, Any]]:
        async with self.db.execute("SELECT data FROM committees WHERE run_id = ? ORDER BY id", (run_id,)) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    # ---------- society feed ----------

    async def save_feed(self, run_id: str, items: list[dict[str, Any]]) -> None:
        await self._many(
            "INSERT OR REPLACE INTO feed (run_id, id, seq, author, data) VALUES (?,?,?,?,?)",
            [(run_id, it["id"], i, it.get("author"), json.dumps(it, default=str)) for i, it in enumerate(items)],
        )

    async def feed(self, run_id: str, author: str | None = None) -> list[dict[str, Any]]:
        if author:
            sql, args = "SELECT data FROM feed WHERE run_id = ? AND author = ? ORDER BY seq", (run_id, author)
        else:
            sql, args = "SELECT data FROM feed WHERE run_id = ? ORDER BY seq", (run_id,)
        async with self.db.execute(sql, args) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    # ---------- chat ----------

    async def chat(self, run_id: str, pid: str) -> list[dict[str, str]]:
        async with self.db.execute("SELECT messages FROM chats WHERE run_id = ? AND persona_id = ?", (run_id, pid)) as cur:
            row = await cur.fetchone()
        return json.loads(row["messages"]) if row else []

    async def save_chat(self, run_id: str, pid: str, messages: list[dict[str, str]]) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO chats (run_id, persona_id, messages) VALUES (?,?,?)",
            (run_id, pid, json.dumps(messages)),
        )

    # ---------- calibration & backtests ----------

    async def calibration(self, kind: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT data FROM calibrations WHERE kind = ?", (kind,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["data"]) if row else None

    async def save_calibration(self, kind: str, data: dict[str, Any]) -> None:
        await self._exec("INSERT OR REPLACE INTO calibrations (kind, data) VALUES (?,?)", (kind, json.dumps(data)))

    async def delete_calibration(self, kind: str) -> None:
        await self._exec("DELETE FROM calibrations WHERE kind = ?", (kind,))

    async def save_backtest(self, bt_id: str, data: dict[str, Any]) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO backtests (id, created_at, data) VALUES (?,?,?)", (bt_id, time.time(), json.dumps(data, default=str))
        )

    async def backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self.db.execute("SELECT id, created_at, data FROM backtests ORDER BY created_at DESC LIMIT ?", (limit,)) as cur:
            return [{"id": r["id"], "created_at": r["created_at"], **json.loads(r["data"])} for r in await cur.fetchall()]


    # ---------- track record ----------

    async def save_prediction(self, data: dict[str, Any]) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO predictions (id, run_id, created_at, data) VALUES (?,?,?,?)",
            (data["id"], data["run_id"], data["created_at"], json.dumps(data)),
        )

    async def predictions(self, run_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT data FROM predictions", ()
        if run_id:
            sql, args = sql + " WHERE run_id = ?", (run_id,)
        async with self.db.execute(sql + " ORDER BY created_at DESC", args) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def prediction(self, pred_id: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT data FROM predictions WHERE id = ?", (pred_id,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["data"]) if row else None

    async def delete_prediction(self, pred_id: str) -> None:
        await self._exec("DELETE FROM predictions WHERE id = ?", (pred_id,))


    # ---------- group interviews ----------

    async def save_interview(self, data: dict[str, Any]) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO interviews (id, run_id, created_at, data) VALUES (?,?,?,?)",
            (data["id"], data["run_id"], data["created_at"], json.dumps(data)),
        )

    async def interviews(self, run_id: str) -> list[dict[str, Any]]:
        async with self.db.execute("SELECT data FROM interviews WHERE run_id = ? ORDER BY created_at DESC", (run_id,)) as cur:
            return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def interview(self, iv_id: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT data FROM interviews WHERE id = ?", (iv_id,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["data"]) if row else None

    async def delete_interview(self, iv_id: str) -> None:
        await self._exec("DELETE FROM interviews WHERE id = ?", (iv_id,))


store = Store()
