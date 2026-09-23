import json
import sqlite3
from pathlib import Path


class Repository:
    def __init__(self, path, initial_backend):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turns(session_id TEXT, turn_id TEXT, request TEXT, response TEXT,
                    PRIMARY KEY(session_id,turn_id));
                CREATE TABLE IF NOT EXISTS backend(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, session_id TEXT, body TEXT);''')
            db.execute('INSERT OR IGNORE INTO backend VALUES(1,?)', (json.dumps(initial_backend),))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def get(self, session_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM sessions WHERE id=?', (session_id,)).fetchone()
            return json.loads(row['body']) if row else None

    def save(self, state, turn=None):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)', (state['conversation_id'], json.dumps(state)))
            if turn:
                db.execute('INSERT INTO turns VALUES(?,?,?,?)', (state['conversation_id'], *turn))

    def previous_turn(self, session_id, turn_id):
        with self.connect() as db:
            row = db.execute('SELECT request,response FROM turns WHERE session_id=? AND turn_id=?', (session_id, turn_id)).fetchone()
            return dict(row) if row else None

    def sessions(self):
        with self.connect() as db:
            return [json.loads(r['body']) for r in db.execute('SELECT body FROM sessions ORDER BY rowid DESC LIMIT 100')]

    def save_event(self, event):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO events VALUES(?,?,?)', (event['event_id'], event['conversation_id'], json.dumps(event)))
        with Path(self.path).with_suffix('.events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n')

    def events(self, session_id=None):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM events WHERE session_id=? ORDER BY rowid DESC LIMIT 100', (session_id,)) if session_id else db.execute('SELECT body FROM events ORDER BY rowid DESC LIMIT 100')
            return [json.loads(r['body']) for r in rows]
