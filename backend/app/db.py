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
            user_id TEXT NOT NULL DEFAULT 'local',
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
            user_id TEXT NOT NULL DEFAULT 'local', persona_id TEXT NOT NULL DEFAULT 'unassigned',
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS persona_memory_settings (
            user_id TEXT NOT NULL DEFAULT 'local', persona_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, persona_id)
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversation_favorites (
            conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'local', persona TEXT NOT NULL, domain TEXT NOT NULL,
            title TEXT NOT NULL, source_path TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
            content TEXT NOT NULL, checksum TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL DEFAULT 'local', persona TEXT NOT NULL, domain TEXT NOT NULL, heading TEXT NOT NULL,
            content TEXT NOT NULL, embedding_json TEXT
        );
        CREATE TABLE IF NOT EXISTS knowledge_source_metadata (
            source_id TEXT PRIMARY KEY REFERENCES knowledge_sources(id) ON DELETE CASCADE,
            creator TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', discipline TEXT NOT NULL DEFAULT '',
            published TEXT NOT NULL DEFAULT '', source_version TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '', scope TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_search_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'local', mode TEXT NOT NULL, persona TEXT NOT NULL,
            query TEXT NOT NULL, method TEXT NOT NULL, hits_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS model_configs (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'local', name TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'custom',
            base_url TEXT NOT NULL, model_id TEXT NOT NULL, protocol TEXT NOT NULL,
            api_key_enc TEXT NOT NULL DEFAULT '', parameters_json TEXT NOT NULL DEFAULT '{}',
            headers_json TEXT NOT NULL DEFAULT '{}', timeout_seconds REAL NOT NULL DEFAULT 120,
            capabilities_json TEXT NOT NULL DEFAULT '{}', input_price_per_million REAL,
            output_price_per_million REAL, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS persona_model_bindings (
            user_id TEXT NOT NULL DEFAULT 'local', persona TEXT PRIMARY KEY, config_id TEXT REFERENCES model_configs(id) ON DELETE SET NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS persona_model_settings (
            user_id TEXT NOT NULL DEFAULT 'local', persona TEXT PRIMARY KEY, temperature REAL, max_output_tokens INTEGER,
            thinking_mode INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS model_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'local', config_id TEXT, persona TEXT NOT NULL,
            provider TEXT NOT NULL, model_id TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
            cost_estimate REAL, cost_basis TEXT NOT NULL DEFAULT 'unknown', status TEXT NOT NULL,
            error_category TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO settings(key, value) VALUES ('memory_enabled','0');
        """)
        additions = {
            "conversations": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "memories": {
                "user_id": "TEXT NOT NULL DEFAULT 'local'",
                "persona_id": "TEXT NOT NULL DEFAULT 'unassigned'",
            },
            "knowledge_sources": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "knowledge_chunks": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "knowledge_search_log": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "model_configs": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "persona_model_bindings": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "persona_model_settings": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
            "model_usage": {"user_id": "TEXT NOT NULL DEFAULT 'local'"},
        }
        for table, columns_to_add in additions.items():
            existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, declaration in columns_to_add.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        columns = {row[1] for row in db.execute("PRAGMA table_info(model_configs)").fetchall()}
        additions = {
            "headers_json": "TEXT NOT NULL DEFAULT '{}'", "timeout_seconds": "REAL NOT NULL DEFAULT 120",
            "capabilities_json": "TEXT NOT NULL DEFAULT '{}'", "input_price_per_million": "REAL",
            "output_price_per_million": "REAL", "enabled": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, declaration in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE model_configs ADD COLUMN {name} {declaration}")
        from .personas import SPACE_PROMPTS
        for persona_id in SPACE_PROMPTS:
            db.execute(
                "INSERT OR IGNORE INTO people(id,name,category,notes,user_id,persona_id) VALUES(?,?,?,?,?,?)",
                (f"user:{persona_id}", "我", "user", "当前人格空间的用户节点", "local", persona_id),
            )
