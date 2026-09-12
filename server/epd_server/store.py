"""Documents a board posts, kept on disk and read back by time.

A project hands :meth:`ReadingsStore.add` to ``DisplayServer(ingest=...)``,
and :class:`~epd_server.source.IngestSource` serves what it holds to the
pages. The store reads two keys of a document and nothing else: ``ts``, the
epoch seconds the board stamped it with, and ``device``, the board that
sent it. The rest is the project's.

A board that did not hear the reply to a POST sends the document again, and
one that held documents while the server was down sends them late and out
of order. So a document is kept by its own ``ts``, not by when it arrived,
and a second document with the same device and ``ts`` is ignored.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS readings ("
    " device TEXT NOT NULL,"
    " ts INTEGER NOT NULL,"
    " doc TEXT NOT NULL,"
    " PRIMARY KEY (device, ts))",
    "CREATE INDEX IF NOT EXISTS readings_ts ON readings (ts)",
)


class ReadingsStore:
    """Timestamped JSON documents in one SQLite table.

    Args:
        path: the database file, created if missing; ``":memory:"`` for one
            that lasts as long as this object.
    """

    def __init__(self, path: str | os.PathLike):
        self.path = os.fspath(path)
        # One connection, shared by the HTTP thread that adds documents and
        # the thread that regenerates pages, so every use takes the lock.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock, self._db:
            for statement in _SCHEMA:
                self._db.execute(statement)

    def add(self, doc: dict) -> bool:
        """Keep ``doc``. False when its device already has a document at its ``ts``.

        Raises:
            ValueError: ``ts`` is not an integer, or ``device`` is not a string.
        """
        ts = doc.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError("ts must be an integer epoch")
        device = doc.get("device", "")
        if not isinstance(device, str):
            raise ValueError("device must be a string")
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO readings (device, ts, doc) VALUES (?, ?, ?)",
                (device, ts, json.dumps(doc, separators=(",", ":"))))
            return cur.rowcount == 1

    def latest(self, device: str | None = None) -> dict | None:
        """The document with the highest ``ts``, or None when there is none."""
        docs = self._select([], [], "ORDER BY ts DESC LIMIT 1", device)
        return docs[0] if docs else None

    def between(self, start: int, end: int | None = None,
                device: str | None = None) -> list[dict]:
        """Documents with ``start <= ts``, and ``ts <= end`` when given, oldest first."""
        where, params = ["ts >= ?"], [start]
        if end is not None:
            where.append("ts <= ?")
            params.append(end)
        return self._select(where, params, "ORDER BY ts", device)

    def count(self, device: str | None = None) -> int:
        where, params = self._device_filter([], [], device)
        sql = "SELECT COUNT(*) FROM readings" + self._where(where)
        with self._lock:
            return self._db.execute(sql, params).fetchone()[0]

    def prune(self, before: int) -> int:
        """Delete every document with ``ts < before``. Returns how many went."""
        with self._lock, self._db:
            return self._db.execute("DELETE FROM readings WHERE ts < ?", (before,)).rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _select(self, where: list[str], params: list, tail: str,
                device: str | None) -> list[dict]:
        where, params = self._device_filter(where, params, device)
        sql = "SELECT doc FROM readings" + self._where(where) + " " + tail
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [json.loads(doc) for (doc,) in rows]

    @staticmethod
    def _device_filter(where: list[str], params: list, device: str | None):
        if device is None:
            return where, params
        return where + ["device = ?"], params + [device]

    @staticmethod
    def _where(clauses: list[str]) -> str:
        return " WHERE " + " AND ".join(clauses) if clauses else ""
