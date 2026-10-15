
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# Store the database in the project directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "spidey_memory.db"


class MemoryStore:
    """Simple, local SQLite storage for explicit Spidey memories."""

    def __init__(self, database_path=DATABASE_PATH):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize_database()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self):
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    memory_key TEXT PRIMARY KEY COLLATE NOCASE,
                    memory_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def save(self, key, value):
        """Save or update a memory using a named key."""
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError("Memory key cannot be empty.")

        if not value:
            raise ValueError("Memory value cannot be empty.")

        timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            connection.execute("""
                INSERT INTO memories (
                    memory_key,
                    memory_value,
                    updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(memory_key) DO UPDATE SET
                    memory_value = excluded.memory_value,
                    updated_at = excluded.updated_at
            """, (key, value, timestamp))

    def get(self, key):
        """Retrieve a memory by key, or return None if absent."""
        with self._connect() as connection:
            row = connection.execute("""
                SELECT memory_value
                FROM memories
                WHERE memory_key = ?
            """, (key.strip(),)).fetchone()

        return row["memory_value"] if row else None

    def list_all(self):
        """Return all memories as dictionaries."""
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT memory_key, memory_value, updated_at
                FROM memories
                ORDER BY memory_key COLLATE NOCASE
            """).fetchall()

        return [dict(row) for row in rows]

    def delete(self, key):
        """Delete a memory by key. Return True if one was deleted."""
        with self._connect() as connection:
            cursor = connection.execute("""
                DELETE FROM memories
                WHERE memory_key = ?
            """, (key.strip(),))

        return cursor.rowcount > 0
