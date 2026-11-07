"""Additive v2 schema migration for Eunoia."""
from pathlib import Path
import sqlite3

CURRENT_VERSION = 3
CORE_VERSION_TABLE = "core_schema_version"

TABLES = [
    "CREATE TABLE IF NOT EXISTS personas (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, system_prompt TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'other', notes TEXT NOT NULL DEFAULT '', hidden INTEGER NOT NULL DEFAULT 0, last_mentioned_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS relationships (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE, target_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE, kind TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('directed','mutual')), strength REAL NOT NULL DEFAULT 0.5 CHECK(strength BETWEEN 0 AND 1), source_type TEXT NOT NULL DEFAULT 'user_report' CHECK(source_type IN ('user_report','observed_event','ai_inference')), confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(source_id,target_id,kind))",
    "CREATE TABLE IF NOT EXISTS important_events (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source_type TEXT NOT NULL DEFAULT 'user_report' CHECK(source_type IN ('user_report','observed_event','ai_inference')), confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1), conversation_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS relationship_events (id TEXT PRIMARY KEY, relationship_id TEXT REFERENCES relationships(id) ON DELETE CASCADE, person_id TEXT REFERENCES people(id) ON DELETE CASCADE, event_id TEXT REFERENCES important_events(id) ON DELETE SET NULL, summary TEXT NOT NULL, occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, strength_before REAL, strength_after REAL, source_type TEXT NOT NULL DEFAULT 'user_report' CHECK(source_type IN ('user_report','observed_event','ai_inference')), confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1), conversation_id TEXT)",
    "CREATE TABLE IF NOT EXISTS emotional_states (id TEXT PRIMARY KEY, person_id TEXT REFERENCES people(id) ON DELETE CASCADE, event_id TEXT REFERENCES important_events(id) ON DELETE SET NULL, emotions_json TEXT NOT NULL, intensity REAL NOT NULL DEFAULT 0.5 CHECK(intensity BETWEEN 0 AND 1), source_type TEXT NOT NULL DEFAULT 'user_report' CHECK(source_type IN ('user_report','observed_event','ai_inference')), confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1), occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, conversation_id TEXT)",
    "CREATE TABLE IF NOT EXISTS counterfactual_cases (id TEXT PRIMARY KEY, title TEXT NOT NULL, background TEXT NOT NULL, assumptions_json TEXT NOT NULL DEFAULT '[]', result_json TEXT NOT NULL DEFAULT '{}', conversation_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS simulation_branches (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES counterfactual_cases(id) ON DELETE CASCADE, parent_id TEXT REFERENCES simulation_branches(id) ON DELETE CASCADE, path_key TEXT NOT NULL, choice TEXT NOT NULL, short_term TEXT NOT NULL DEFAULT '', mid_term TEXT NOT NULL DEFAULT '', long_term TEXT NOT NULL DEFAULT '', gains_json TEXT NOT NULL DEFAULT '[]', costs_json TEXT NOT NULL DEFAULT '[]', uncertainties_json TEXT NOT NULL DEFAULT '[]')",
    "CREATE TABLE IF NOT EXISTS analysis_reports (id TEXT PRIMARY KEY, conversation_id TEXT, report_type TEXT NOT NULL, content_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS memory_confirmations (id TEXT PRIMARY KEY, memory_id INTEGER, subject_id TEXT, field TEXT NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', source_type TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.5, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT)",
]

def migrate(path: Path) -> None:
    version = 0
    if path.exists():
        with sqlite3.connect(path) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (CORE_VERSION_TABLE,)).fetchone():
                version = db.execute(f"SELECT COALESCE(MAX(version),0) FROM {CORE_VERSION_TABLE}").fetchone()[0]
        if version >= CURRENT_VERSION:
            return
        stem = path.name[:-len(path.suffix)] if path.suffix else path.name
        backup = path.with_name(stem + f".pre-core-v{CURRENT_VERSION}-backup" + path.suffix)
        if not backup.exists():
            with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
                source.backup(target)
        with sqlite3.connect(backup) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError(f"Eunoia v{CURRENT_VERSION} database backup failed integrity check")
            with sqlite3.connect(path) as source:
                original = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            copied = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not original.issubset(copied):
                raise RuntimeError(f"Eunoia v{CURRENT_VERSION} backup is missing original tables")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN")
        try:
            db.execute(f"CREATE TABLE IF NOT EXISTS {CORE_VERSION_TABLE} (version INTEGER NOT NULL)")
            if not db.execute(f"SELECT 1 FROM {CORE_VERSION_TABLE} LIMIT 1").fetchone():
                db.execute(f"INSERT INTO {CORE_VERSION_TABLE}(version) VALUES (0)")
            for statement in TABLES:
                db.execute(statement)
            if CURRENT_VERSION >= 3:
                scoped_tables = (
                    "people", "relationships", "important_events", "relationship_events",
                    "emotional_states", "counterfactual_cases", "analysis_reports",
                )
                for table in scoped_tables:
                    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
                    if "user_id" not in columns:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
                    if "persona_id" not in columns:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN persona_id TEXT NOT NULL DEFAULT 'unassigned'")
                for table in ("important_events", "relationship_events", "emotional_states", "counterfactual_cases", "analysis_reports"):
                    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
                    has_conversations = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone()
                    if "conversation_id" in columns and has_conversations:
                        db.execute(
                            f"UPDATE {table} SET persona_id=CASE COALESCE((SELECT mode FROM conversations WHERE conversations.id={table}.conversation_id),'unassigned') WHEN 'reflect' THEN 'guidance' WHEN 'relationship' THEN 'anatomy' WHEN 'simulation' THEN 'guidance' WHEN 'vent' THEN 'anatomy' WHEN 'self' THEN 'self_exploration' ELSE COALESCE((SELECT mode FROM conversations WHERE conversations.id={table}.conversation_id),'unassigned') END WHERE persona_id='unassigned' AND conversation_id IS NOT NULL"
                        )
                # Records with no traceable conversation remain unassigned and are never exposed in a persona space.
            db.execute("INSERT OR IGNORE INTO personas(id,name,role,system_prompt) VALUES (?,?,?,?)", ('empathetic','温柔导师','empathetic_mentor','温柔理解情绪，辨认需求、恐惧与矛盾；不批判，不替用户下结论。'))
            db.execute("INSERT OR IGNORE INTO personas(id,name,role,system_prompt) VALUES (?,?,?,?)", ('rational','理性观察者','rational_observer','依据事实、证据、逻辑与现实限制分析；区分事实、解释和未知，不为安慰而改变结论。'))
            db.execute("INSERT OR IGNORE INTO people(id,name,category,notes) VALUES (?,?,?,?)", ('user','我','user','系统保留的用户节点'))
            db.execute(f"UPDATE {CORE_VERSION_TABLE} SET version=?", (CURRENT_VERSION,))
            db.commit()
        except Exception:
            db.rollback()
            raise
