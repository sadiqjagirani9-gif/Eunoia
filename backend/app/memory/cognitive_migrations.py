"""Version 3 cognitive profile tables; additive and transactionally applied."""
import sqlite3
from pathlib import Path

VERSION=3
STATEMENTS=(
"CREATE TABLE IF NOT EXISTS cognitive_observations(id TEXT PRIMARY KEY,dimension TEXT NOT NULL,statement TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',source_type TEXT NOT NULL,evidence_count INTEGER NOT NULL DEFAULT 1,distinct_contexts INTEGER NOT NULL DEFAULT 1,supporting_json TEXT NOT NULL DEFAULT '[]',counter_evidence_json TEXT NOT NULL DEFAULT '[]',confidence_level TEXT NOT NULL DEFAULT '极低',source_conversation_id TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,user_explanation TEXT NOT NULL DEFAULT '')",
"CREATE TABLE IF NOT EXISTS cognitive_evidence(id TEXT PRIMARY KEY,observation_id TEXT NOT NULL REFERENCES cognitive_observations(id) ON DELETE CASCADE,conversation_id TEXT,message_id INTEGER,evidence TEXT NOT NULL,evidence_type TEXT NOT NULL DEFAULT 'support',source_type TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_snapshots(id TEXT PRIMARY KEY,reason TEXT NOT NULL DEFAULT 'manual',profile_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_evolution(id TEXT PRIMARY KEY,dimension TEXT NOT NULL,summary TEXT NOT NULL,past_behavior TEXT NOT NULL DEFAULT '',recent_behavior TEXT NOT NULL DEFAULT '',evidence_json TEXT NOT NULL DEFAULT '[]',possible_causes TEXT NOT NULL DEFAULT '',uncertainties TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_contradictions(id TEXT PRIMARY KEY,observation_id TEXT REFERENCES cognitive_observations(id) ON DELETE SET NULL,past_statement TEXT NOT NULL,current_statement TEXT NOT NULL,question TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',user_response TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT)",
"CREATE TABLE IF NOT EXISTS cognitive_feedback(id TEXT PRIMARY KEY,observation_id TEXT NOT NULL REFERENCES cognitive_observations(id) ON DELETE CASCADE,rating TEXT NOT NULL,explanation TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS short_term_memories(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,content_json TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
)

def migrate_cognitive(path: Path)->None:
    if path.exists():
        with sqlite3.connect(path) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
            version=db.execute('SELECT COALESCE(MAX(version),0) FROM schema_version').fetchone()[0] if exists else 0
        if version>=VERSION:return
        stem=path.name[:-len(path.suffix)] if path.suffix else path.name
        backup=path.with_name(stem+'.pre-v3-backup'+path.suffix)
        if not backup.exists():
            with sqlite3.connect(path) as source,sqlite3.connect(backup) as target: source.backup(target)
        with sqlite3.connect(backup) as check:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('V3 database backup integrity check failed')
            with sqlite3.connect(path) as source:
                original={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            copied={row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not original.issubset(copied):raise RuntimeError('V3 database backup is missing original tables')
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)')
            if not db.execute('SELECT 1 FROM schema_version LIMIT 1').fetchone():db.execute('INSERT INTO schema_version(version) VALUES(0)')
            for statement in STATEMENTS:db.execute(statement)
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('cognitive_enabled','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('memory_updates_enabled','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('require_confirmation','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('short_term_days','30')")
            db.execute('UPDATE schema_version SET version=?',(VERSION,))
            db.commit()
        except Exception:
            db.rollback();raise
