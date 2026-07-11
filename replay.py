from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class ReplayLedger:
    """Atomic, bounded replay ledger for a single sandbox instance."""

    def __init__(self, path: Path, retention_seconds: int = 900) -> None:
        self.path = path
        self.retention_seconds = retention_seconds
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS executions "
                "(execution_id TEXT PRIMARY KEY, accepted_at INTEGER NOT NULL)"
            )

    def claim(self, execution_id: str, accepted_at: int | None = None) -> bool:
        now = accepted_at or int(time.time())
        with self._lock, self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            database.execute(
                "DELETE FROM executions WHERE accepted_at < ?",
                (now - self.retention_seconds,),
            )
            try:
                database.execute(
                    "INSERT INTO executions (execution_id, accepted_at) VALUES (?, ?)",
                    (execution_id, now),
                )
            except sqlite3.IntegrityError:
                database.rollback()
                return False
            database.commit()
            return True

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=2, isolation_level=None)
