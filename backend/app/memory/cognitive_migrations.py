"""Additive cognitive profile migrations with verified SQLite backups."""
import sqlite3
from pathlib import Path

VERSION=6
STATEMENTS=(
"CREATE TABLE IF NOT EXISTS cognitive_observations(id TEXT PRIMARY KEY,dimension TEXT NOT NULL,statement TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',source_type TEXT NOT NULL,evidence_count INTEGER NOT NULL DEFAULT 1,distinct_contexts INTEGER NOT NULL DEFAULT 1,supporting_json TEXT NOT NULL DEFAULT '[]',counter_evidence_json TEXT NOT NULL DEFAULT '[]',confidence_level TEXT NOT NULL DEFAULT '极低',source_conversation_id TEXT,persona_id TEXT NOT NULL DEFAULT 'unassigned',user_id TEXT NOT NULL DEFAULT 'local',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,user_explanation TEXT NOT NULL DEFAULT '')",
"CREATE TABLE IF NOT EXISTS cognitive_evidence(id TEXT PRIMARY KEY,observation_id TEXT NOT NULL REFERENCES cognitive_observations(id) ON DELETE CASCADE,conversation_id TEXT,message_id INTEGER,evidence TEXT NOT NULL,evidence_type TEXT NOT NULL DEFAULT 'support',source_type TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_snapshots(id TEXT PRIMARY KEY,reason TEXT NOT NULL DEFAULT 'manual',profile_json TEXT NOT NULL,persona_id TEXT NOT NULL DEFAULT 'unassigned',user_id TEXT NOT NULL DEFAULT 'local',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_evolution(id TEXT PRIMARY KEY,dimension TEXT NOT NULL,summary TEXT NOT NULL,past_behavior TEXT NOT NULL DEFAULT '',recent_behavior TEXT NOT NULL DEFAULT '',evidence_json TEXT NOT NULL DEFAULT '[]',possible_causes TEXT NOT NULL DEFAULT '',uncertainties TEXT NOT NULL DEFAULT '',persona_id TEXT NOT NULL DEFAULT 'unassigned',user_id TEXT NOT NULL DEFAULT 'local',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_contradictions(id TEXT PRIMARY KEY,observation_id TEXT REFERENCES cognitive_observations(id) ON DELETE SET NULL,past_statement TEXT NOT NULL,current_statement TEXT NOT NULL,question TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',user_response TEXT NOT NULL DEFAULT '',persona_id TEXT NOT NULL DEFAULT 'unassigned',user_id TEXT NOT NULL DEFAULT 'local',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT)",
"CREATE TABLE IF NOT EXISTS cognitive_feedback(id TEXT PRIMARY KEY,observation_id TEXT NOT NULL REFERENCES cognitive_observations(id) ON DELETE CASCADE,rating TEXT NOT NULL,explanation TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS short_term_memories(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,content_json TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE TABLE IF NOT EXISTS cognitive_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
"CREATE TABLE IF NOT EXISTS cognitive_rejections(id TEXT PRIMARY KEY,user_id TEXT NOT NULL DEFAULT 'local',fingerprint TEXT NOT NULL,statement TEXT NOT NULL,dimension TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,fingerprint))",
"CREATE TABLE IF NOT EXISTS cognitive_exclusions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL DEFAULT 'local',topic TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,topic))",
)

def migrate_cognitive(path: Path)->None:
    if path.exists():
        with sqlite3.connect(path) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
            version=db.execute('SELECT COALESCE(MAX(version),0) FROM schema_version').fetchone()[0] if exists else 0
        if version>=VERSION:return
        stem=path.name[:-len(path.suffix)] if path.suffix else path.name
        backup=path.with_name(stem+f'.pre-cognitive-v{VERSION}-backup'+path.suffix)
        if not backup.exists():
            with sqlite3.connect(path) as source,sqlite3.connect(backup) as target: source.backup(target)
        with sqlite3.connect(backup) as check:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError(f'Cognitive v{VERSION} database backup integrity check failed')
            with sqlite3.connect(path) as source:
                original={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            copied={row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not original.issubset(copied):raise RuntimeError(f'Cognitive v{VERSION} backup is missing original tables')
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)')
            if not db.execute('SELECT 1 FROM schema_version LIMIT 1').fetchone():db.execute('INSERT INTO schema_version(version) VALUES(0)')
            for statement in STATEMENTS:db.execute(statement)
            scoped_columns={
                'cognitive_observations':{'persona_id':"TEXT NOT NULL DEFAULT 'unassigned'",'user_id':"TEXT NOT NULL DEFAULT 'local'",'evidence_class':"TEXT NOT NULL DEFAULT 'hypothesis'",'context_note':"TEXT NOT NULL DEFAULT ''",'alternative_explanation':"TEXT NOT NULL DEFAULT ''",'fingerprint':"TEXT NOT NULL DEFAULT ''",'claim_kind':"TEXT NOT NULL DEFAULT 'observation'"},
                'cognitive_evidence':{'context_note':"TEXT NOT NULL DEFAULT ''"},
                'cognitive_rejections':{'dimension':"TEXT NOT NULL DEFAULT ''"},
                'cognitive_snapshots':{'persona_id':"TEXT NOT NULL DEFAULT 'unassigned'",'user_id':"TEXT NOT NULL DEFAULT 'local'"},
                'cognitive_evolution':{'persona_id':"TEXT NOT NULL DEFAULT 'unassigned'",'user_id':"TEXT NOT NULL DEFAULT 'local'"},
                'cognitive_contradictions':{'persona_id':"TEXT NOT NULL DEFAULT 'unassigned'",'user_id':"TEXT NOT NULL DEFAULT 'local'",'past_context':"TEXT NOT NULL DEFAULT ''",'current_context':"TEXT NOT NULL DEFAULT ''",'possible_causes':"TEXT NOT NULL DEFAULT ''",'source_conversation_id':"TEXT"},
            }
            for table,columns in scoped_columns.items():
                existing={row[1] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}
                for name,declaration in columns.items():
                    if name not in existing:db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone() and 'mode' in {row[1] for row in db.execute('PRAGMA table_info(conversations)').fetchall()}:
                db.execute("UPDATE cognitive_observations SET persona_id=COALESCE((SELECT mode FROM conversations WHERE conversations.id=cognitive_observations.source_conversation_id),'unassigned') WHERE persona_id='unassigned'")
                db.execute("UPDATE cognitive_observations SET persona_id=CASE persona_id WHEN 'reflect' THEN 'guidance' WHEN 'relationship' THEN 'anatomy' WHEN 'simulation' THEN 'guidance' WHEN 'vent' THEN 'anatomy' WHEN 'self' THEN 'self_exploration' ELSE persona_id END WHERE persona_id IN ('reflect','relationship','simulation','vent','self')")
                db.execute("UPDATE cognitive_contradictions SET persona_id=COALESCE((SELECT persona_id FROM cognitive_observations WHERE id=cognitive_contradictions.observation_id),'unassigned') WHERE persona_id='unassigned'")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('cognitive_enabled','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('memory_updates_enabled','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('require_confirmation','1')")
            db.execute("INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES('short_term_days','30')")
            db.execute('UPDATE schema_version SET version=?',(VERSION,))
            db.commit()
        except Exception:
            db.rollback();raise
