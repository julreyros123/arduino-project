import os
import sqlite3
import uuid as _uuid
from datetime import datetime

class ReactionTimeStorage:
    def __init__(self, db_path='data/results.db'):
        self.db_path = db_path
        self._ensure_parent_directory()
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.create_table()
        self._ensure_participant_column()
        self._ensure_participants_table()
        self._ensure_profession_column()
        self._ensure_session_id_column()
        self._ensure_participant_uuid_column()

    def create_table(self):
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS reaction_times (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    participant_name TEXT,
                    reaction_time REAL NOT NULL
                )
            ''')

    def _ensure_participant_column(self):
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(reaction_times)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'participant_name' not in columns:
            with self.connection:
                self.connection.execute(
                    "ALTER TABLE reaction_times ADD COLUMN participant_name TEXT"
                )

    def _ensure_participants_table(self):
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    age INTEGER,
                    gender TEXT,
                    profession TEXT,
                    registered_at TEXT NOT NULL
                )
            ''')

    def _ensure_profession_column(self):
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(participants)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'profession' not in columns:
            with self.connection:
                self.connection.execute(
                    "ALTER TABLE participants ADD COLUMN profession TEXT"
                )

    def _ensure_session_id_column(self):
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(reaction_times)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'session_id' not in columns:
            with self.connection:
                self.connection.execute(
                    "ALTER TABLE reaction_times ADD COLUMN session_id TEXT"
                )

    def _ensure_participant_uuid_column(self):
        """Add participant_uuid to the participants table and backfill any NULL rows."""
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA table_info(participants)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'participant_uuid' not in columns:
            with self.connection:
                self.connection.execute(
                    "ALTER TABLE participants ADD COLUMN participant_uuid TEXT"
                )
        # Backfill rows that have no UUID (first run after migration).
        cursor.execute("SELECT id FROM participants WHERE participant_uuid IS NULL")
        rows = cursor.fetchall()
        if rows:
            with self.connection:
                for row in rows:
                    self.connection.execute(
                        "UPDATE participants SET participant_uuid = ? WHERE id = ?",
                        (str(_uuid.uuid4()), row[0]),
                    )

    def _ensure_parent_directory(self):
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    def save_reaction_time(self, participant_name, reaction_time_ms, session_id=None):
        timestamp = datetime.now().isoformat()
        with self.connection:
            self.connection.execute('''
                INSERT INTO reaction_times (timestamp, participant_name, reaction_time, session_id)
                VALUES (?, ?, ?, ?)
            ''', (timestamp, participant_name, reaction_time_ms, session_id))

    def get_all_reaction_times(self):
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM reaction_times ORDER BY id DESC')
        return cursor.fetchall()

    def get_session_averages(self):
        """Return one row per session: (timestamp, participant_name, avg_rt, trial_count).
        Rows without a session_id (legacy data) are each treated as their own session."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT
                MIN(timestamp)             AS timestamp,
                participant_name,
                ROUND(AVG(reaction_time), 1) AS avg_rt,
                COUNT(*)                   AS trial_count
            FROM reaction_times
            GROUP BY COALESCE(session_id, CAST(id AS TEXT))
            ORDER BY MIN(id) DESC
        ''')
        return cursor.fetchall()

    # ── Participant registry ──────────────────────────────────────────────────

    def save_participant(self, name: str, age: int, gender: str,
                         profession: str = "") -> None:
        """Insert or update a participant record, preserving their UUID on update."""
        registered_at = datetime.now().isoformat()
        # Preserve the existing UUID when updating; assign a fresh one for new registrations.
        existing = self.get_participant(name)
        participant_uuid = (
            existing["participant_uuid"]
            if (existing and existing["participant_uuid"])
            else str(_uuid.uuid4())
        )
        with self.connection:
            self.connection.execute('''
                INSERT INTO participants (name, age, gender, profession, registered_at, participant_uuid)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    age           = excluded.age,
                    gender        = excluded.gender,
                    profession    = excluded.profession,
                    registered_at = excluded.registered_at
            ''', (name, age, gender, profession or "", registered_at, participant_uuid))

    def get_all_participants(self):
        """Return all participants ordered by registration date (newest first)."""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM participants ORDER BY registered_at DESC')
        return cursor.fetchall()

    def get_participant(self, name: str):
        """Return a single participant by exact name, or None."""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM participants WHERE name = ?', (name,))
        return cursor.fetchone()

    def get_participant_ci(self, name: str):
        """Case-insensitive name lookup. Returns the first match or None."""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM participants WHERE LOWER(name) = LOWER(?)', (name,))
        return cursor.fetchone()

    def get_participant_by_uuid(self, participant_uuid: str):
        """Return a single participant by their permanent UUID, or None."""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM participants WHERE participant_uuid = ?', (participant_uuid,))
        return cursor.fetchone()

    def get_participant_stats(self, name: str):
        """Return (trial_count, avg_ms, best_ms) for a participant."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) as trials,
                   AVG(reaction_time) as avg_rt,
                   MIN(reaction_time) as best_rt
            FROM reaction_times
            WHERE participant_name = ?
        ''', (name,))
        return cursor.fetchone()

    def get_participant_reaction_times(self, name: str):
        """Return all reaction-time records for a participant, oldest first."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT timestamp, reaction_time
            FROM reaction_times
            WHERE participant_name = ?
            ORDER BY id ASC
        ''', (name,))
        return cursor.fetchall()

    def close(self):
        self.connection.close()