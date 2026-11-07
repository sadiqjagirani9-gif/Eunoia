from pathlib import Path
import asyncio
import sqlite3

from app.migrations import migrate
from app import advanced
from app.advanced import EMPATHETIC, RATIONAL
from app.db import connect, init_db
from app.persona_context import create_persona_context
from app.personas import system_prompt_for


def test_v3_migration_is_additive_scoped_and_idempotent(tmp_path: Path):
    path = tmp_path / 'eunoia.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL)')
        db.execute("INSERT INTO conversations VALUES ('old','历史','reflect')")
        db.execute("CREATE TABLE analysis_reports(id TEXT PRIMARY KEY, conversation_id TEXT, report_type TEXT NOT NULL, content_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO analysis_reports(id,conversation_id,report_type,content_json) VALUES('linked','old','dual','{}')")
        db.execute("INSERT INTO analysis_reports(id,report_type,content_json) VALUES('legacy','dual','{}')")
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM conversations WHERE id='old'").fetchone()[0] == '历史'
        assert db.execute("SELECT name FROM people WHERE id='user'").fetchone()[0] == '我'
        assert db.execute("SELECT version FROM core_schema_version").fetchone()[0] == 3
        assert db.execute("SELECT persona_id FROM analysis_reports WHERE id='linked'").fetchone()[0] == 'guidance'
        assert db.execute("SELECT persona_id FROM analysis_reports WHERE id='legacy'").fetchone()[0] == 'unassigned'
        assert {row[1] for row in db.execute('PRAGMA table_info(relationships)')} >= {'user_id','persona_id'}
    assert path.with_name('eunoia.pre-core-v3-backup.sqlite3').exists()


def test_dual_personas_use_independent_prompts():
    assert EMPATHETIC != RATIONAL
    assert '情绪' in EMPATHETIC
    assert '事实' in RATIONAL


def test_fresh_database_initializes_with_scoped_advanced_tables(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    init_db()
    with sqlite3.connect(tmp_path / 'eunoia.sqlite3') as db:
        for table in ('people','relationships','important_events','relationship_events','emotional_states','counterfactual_cases','analysis_reports'):
            columns={row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            assert {'user_id','persona_id'} <= columns


def test_dual_analysis_keeps_models_prompts_and_observations_separate(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    init_db()
    with connect() as db:
        for persona in ('anatomy', 'debate', 'felix'):
            db.execute("INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES(?,?,?,?,?,?,?)", (persona, 'emotion', f'{persona} private', 'confirmed', 'user_report', persona, 'local'))
    calls = []
    monkeypatch.setattr(advanced.model_config, 'resolve', lambda context: {'id': getattr(context, 'persona_id', context)})

    async def fake_complete(config, messages):
        calls.append((config['id'], messages))
        return f"answer-{len(calls)}"

    monkeypatch.setattr(advanced.llm, 'complete_chat', fake_complete)
    result = asyncio.run(advanced.dual_analysis('一次谈话', create_persona_context('felix')))
    assert result['empathetic'] == 'answer-2'
    assert [item[0] for item in calls] == ['anatomy', 'anatomy', 'debate', 'anatomy']
    for persona, messages in calls:
        assert messages[0]['content'].startswith(system_prompt_for(persona))
        assert 'private' not in messages[0]['content']
        text = '\n'.join(message['content'] for message in messages[1:])
        assert 'felix private' not in text
        if persona == 'debate':
            assert 'debate private' in text
            assert 'anatomy private' not in text


def test_simulation_uses_request_persona_model_and_memory(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    init_db()
    with connect() as db:
        db.execute("INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES('lucien','value','lucien private','confirmed','user_report','lucien','local')")
        db.execute("INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES('guidance','value','guidance private','confirmed','user_report','guidance','local')")
    calls = []
    monkeypatch.setattr(advanced.model_config, 'resolve', lambda context: {'id': getattr(context, 'persona_id', context)})

    async def fake_complete(config, messages):
        calls.append((config, messages))
        return '{"branches":[]}'

    monkeypatch.setattr(advanced.llm, 'complete_chat', fake_complete)
    result = asyncio.run(advanced.simulate('一个选择', create_persona_context('lucien')))
    assert result['result'] == {'branches': []}
    assert calls[0][0]['id'] == 'lucien'
    assert calls[0][1][0]['content'].startswith(system_prompt_for('lucien'))
    assert 'lucien private' in calls[0][1][1]['content']
    assert 'guidance private' not in calls[0][1][1]['content']
