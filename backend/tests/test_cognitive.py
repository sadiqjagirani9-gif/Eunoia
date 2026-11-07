import sqlite3
from pathlib import Path

from app.memory.cognitive_migrations import migrate_cognitive
from app.cognitive_engine.confidence_engine import confidence_label, can_form_observation
from app.cognitive_engine.contradiction_detector import detect


def test_v3_migration_preserves_existing_data_and_is_idempotent(tmp_path: Path):
    path=tmp_path/'eunoia.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT)')
        db.execute("INSERT INTO conversations VALUES('legacy','原有对话')")
        db.execute('CREATE TABLE schema_version(version INTEGER NOT NULL)')
        db.execute('INSERT INTO schema_version VALUES(2)')
    migrate_cognitive(path)
    migrate_cognitive(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM conversations WHERE id='legacy'").fetchone()[0]=='原有对话'
        assert db.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]==6
        assert db.execute("SELECT COUNT(*) FROM cognitive_settings").fetchone()[0]>=3
    backup=path.with_name('eunoia.pre-cognitive-v6-backup.sqlite3')
    assert backup.exists()
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_confidence_requires_repeated_evidence():
    assert confidence_label(1,distinct_contexts=1)=='极低'
    assert confidence_label(3,distinct_contexts=2)=='较低'
    assert confidence_label(6,distinct_contexts=3)=='中等'
    assert confidence_label(12,True,5)=='极低'
    assert can_form_observation(3,2)
    assert not can_form_observation(1,1)


def test_possible_value_tension_is_asked_as_a_question():
    result=detect('我一直强调独立。','我最近希望有人能稳定陪伴和支持我。')
    assert result is not None
    assert result['status']=='pending'
    assert '变化' in result['question'] or '并存' in result['question']
