from pathlib import Path
import sqlite3

from app.migrations import migrate
from app.advanced import EMPATHETIC, RATIONAL


def test_v2_migration_is_additive_and_idempotent(tmp_path: Path):
    path = tmp_path / 'eunoia.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL)')
        db.execute("INSERT INTO conversations VALUES ('old','历史','reflect')")
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM conversations WHERE id='old'").fetchone()[0] == '历史'
        assert db.execute("SELECT name FROM people WHERE id='user'").fetchone()[0] == '我'
        assert db.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    assert path.with_name('eunoia.pre-v2-backup.sqlite3').exists()


def test_dual_personas_use_independent_prompts():
    assert EMPATHETIC != RATIONAL
    assert '情绪' in EMPATHETIC
    assert '事实' in RATIONAL
