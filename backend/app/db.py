import os
import sqlite3
from pathlib import Path


def database_path() -> Path:
    root = Path(os.environ.get("EUNOIA_DATA_DIR", Path.home() / "AppData" / "Local" / "Eunoia"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "eunoia.sqlite3"


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(database_path(), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    from .migrations import migrate
    migrate(database_path())
    from .memory.cognitive_migrations import migrate_cognitive
    migrate_cognitive(database_path())
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'reflect',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
            analysis_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, content TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('fact','self_report','hypothesis')),
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversation_favorites (
            conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id TEXT PRIMARY KEY, persona TEXT NOT NULL, domain TEXT NOT NULL,
            title TEXT NOT NULL, source_path TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
            content TEXT NOT NULL, checksum TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
            persona TEXT NOT NULL, domain TEXT NOT NULL, heading TEXT NOT NULL,
            content TEXT NOT NULL, embedding_json TEXT
        );
        INSERT OR IGNORE INTO settings(key, value) VALUES ('memory_enabled','0');
        """)
