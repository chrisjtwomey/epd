"""Log lines boards publish over MQTT, kept on disk and read back in order.

Each board publishes to its own topic under one prefix, so the subscriber
knows which board a line came from without reading the line. The store keeps
that name, the time the line arrived, its level where the line states one,
and the line as sent. The arrival time is the server's: a board's clock is
unset until it syncs, and the lines before that are the ones worth reading.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from typing import Callable

# Least to most severe, as the firmware names them.
LEVELS = ("DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL")

# A line is "<level> - <message>", or "<stamp> - <level> - <message>".
_LEVEL = re.compile(r"^(?:\S+ - )?(" + "|".join(LEVELS) + r") - ")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS lines ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " board TEXT NOT NULL,"
    " received REAL NOT NULL,"
    " level INTEGER,"
    " text TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS lines_received ON lines (received)",
    # A line is the same line only if the same board sent the same text at
    # the same moment: what lets a file of them be imported twice harmlessly.
    "CREATE UNIQUE INDEX IF NOT EXISTS lines_line ON lines (board, received, text)",
)


def level_of(text: str) -> int | None:
    """The line's level as an index into LEVELS, or None when it states none."""
    m = _LEVEL.match(text)
    return LEVELS.index(m.group(1)) if m else None


class LogStore:
    """Board log lines in one SQLite table, numbered as they arrive.

    Args:
        path: the database file, created if missing; ``":memory:"`` for one
            that lasts as long as this object.
        keep_days: lines older than this are deleted as new ones arrive;
            0 keeps every line.
    """

    # Deleting old lines is a query of its own, so it runs once in this many adds.
    PRUNE_EVERY = 500

    def __init__(self, path: str | os.PathLike, keep_days: float = 0,
                 now: Callable[[], float] = time.time):
        self.path = os.fspath(path)
        self.keep_days = keep_days
        self.now = now
        self._adds = 0
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock, self._db:
            for statement in _SCHEMA:
                self._db.execute(statement)

    def add(self, board: str, text: str) -> int | None:
        """Keep one line from ``board``. Returns its number, or None when the
        store holds that line already."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO lines (board, received, level, text) VALUES (?, ?, ?, ?)",
                (board, self.now(), level_of(text), text))
            number = cursor.lastrowid if cursor.rowcount == 1 else None
        self._adds += 1
        if self.keep_days and self._adds % self.PRUNE_EVERY == 0:
            self.prune(self.now() - self.keep_days * 86400)
        return number

    def lines(self, *, after: int | None = None, before: int | None = None,
              board: str | None = None, level: int | None = None,
              contains: str | None = None, limit: int = 200) -> list[dict]:
        """Up to ``limit`` lines, oldest first, that match every filter given.

        ``after`` gives the lines just after that number, for a reader that
        follows new ones; ``before`` the lines just before it, for one that
        reads back; neither gives the newest. ``level`` keeps lines at that
        level or above, and drops lines that state none.
        """
        where, params = [], []
        if after is not None:
            where.append("id > ?")
            params.append(after)
        if before is not None:
            where.append("id < ?")
            params.append(before)
        if board is not None:
            where.append("board = ?")
            params.append(board)
        if level is not None:
            where.append("level >= ?")
            params.append(level)
        if contains:
            escaped = contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("text LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        order = "ASC" if after is not None else "DESC"
        sql = ("SELECT id, board, received, level, text FROM lines"
               + (" WHERE " + " AND ".join(where) if where else "")
               + f" ORDER BY id {order} LIMIT ?")
        with self._lock:
            rows = self._db.execute(sql, params + [limit]).fetchall()
        if order == "DESC":
            rows.reverse()
        return [{"id": i, "board": b, "received": r,
                 "level": LEVELS[lv] if lv is not None else None, "text": t}
                for i, b, r, lv, t in rows]

    def boards(self) -> list[str]:
        """Every board with a line in the store, by name."""
        with self._lock:
            return [b for (b,) in self._db.execute(
                "SELECT DISTINCT board FROM lines ORDER BY board")]

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM lines").fetchone()[0]

    def prune(self, before: float) -> int:
        """Delete every line that arrived before ``before``. Returns how many went."""
        with self._lock, self._db:
            return self._db.execute("DELETE FROM lines WHERE received < ?", (before,)).rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()
