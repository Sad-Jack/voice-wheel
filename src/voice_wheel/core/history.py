"""SQLite-backed history of the last N results.

Written from the worker thread and read from the main thread (for the tray
menu), so all access is guarded by a lock and the connection is opened with
``check_same_thread=False``.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    created_at: float
    ring: str
    sector: str
    transcript: str
    result: str


class History:
    def __init__(self, db_path: Path, limit: int = 10) -> None:
        self.limit = limit
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    ring TEXT NOT NULL,
                    sector TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    result TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def add(self, ring: str, sector: str, transcript: str, result: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO history (created_at, ring, sector, transcript, result)"
                " VALUES (?, ?, ?, ?, ?)",
                (time.time(), ring, sector, transcript, result),
            )
            self._conn.commit()
            new_id = int(cur.lastrowid or 0)
            self._prune_locked()
            return new_id

    def recent(self, n: int | None = None) -> list[HistoryEntry]:
        n = n or self.limit
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return [
            HistoryEntry(
                id=r["id"],
                created_at=r["created_at"],
                ring=r["ring"],
                sector=r["sector"],
                transcript=r["transcript"],
                result=r["result"],
            )
            for r in rows
        ]

    def _prune_locked(self) -> None:
        """Keep only the newest ``limit`` rows. Caller holds the lock."""
        self._conn.execute(
            "DELETE FROM history WHERE id NOT IN ("
            "  SELECT id FROM history ORDER BY id DESC LIMIT ?"
            ")",
            (self.limit,),
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
