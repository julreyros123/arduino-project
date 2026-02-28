import os
import sqlite3
from datetime import datetime

class ReactionTimeStorage:
    def __init__(self, db_path='data/results.db'):
        self.db_path = db_path
        self._ensure_parent_directory()
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.create_table()
        self._ensure_participant_column()

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

    def _ensure_parent_directory(self):
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    def save_reaction_time(self, participant_name, reaction_time_ms):
        timestamp = datetime.now().isoformat()
        with self.connection:
            self.connection.execute('''
                INSERT INTO reaction_times (timestamp, participant_name, reaction_time)
                VALUES (?, ?, ?)
            ''', (timestamp, participant_name, reaction_time_ms))

    def get_all_reaction_times(self):
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM reaction_times ORDER BY id DESC')
        return cursor.fetchall()

    def close(self):
        self.connection.close()