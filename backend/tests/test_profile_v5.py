import json

from fastapi.testclient import TestClient

from app import main as main_module
from app.db import connect
from app.main import app
from app.profile.profile_updater import extract_signals


def test_extraction_is_conservative_and_contextual():
    assert extract_signals('她说自己很焦虑。') == []
    assert extract_signals('焦虑') == []
    signals = extract_signals('我最近感到焦虑，尤其是在等待重要回复时。')
    assert len(signals) == 1
    assert signals[0]['dimension'] == 'emotion'
    assert signals[0]['statement'].startswith('我最近感到焦虑')
    assert signals[0]['evidence_class'] == 'situational'
    planned = extract_signals('我计划下周开始准备新的职业申请。')[0]
    assert planned['dimension'] == 'decisions'
    assert '不能视为已采取行动' in planned['context_note']


def test_evidence_repetition_requires_time_and_context_and_user_can_reject(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    text = '我最近感到焦虑，尤其是在等待重要回复时。'
    with TestClient(app) as client:
        ids = [client.post('/api/conversations', json={'mode': 'anatomy'}).json()['id'] for _ in range(3)]
        first = client.post('/api/cognitive/observe', json={'content': text, 'persona_id': 'anatomy', 'conversation_id': ids[0]}).json()
        observation_id = first['candidates'][0]['id']
        repeated_same_message = client.post('/api/cognitive/observe', json={'content': text, 'persona_id': 'anatomy', 'conversation_id': ids[0]}).json()
        assert repeated_same_message['candidates'] == []
        with connect() as db:
            db.execute("UPDATE cognitive_evidence SET created_at=datetime('now','-8 days') WHERE observation_id=?", (observation_id,))
        for conversation_id in ids[1:]:
            client.post('/api/cognitive/observe', json={'content': text, 'persona_id': 'anatomy', 'conversation_id': conversation_id})
        item = next(row for row in client.get('/api/cognitive/unified-profile').json()['all_observations'] if row['id'] == observation_id)
        assert item['evidence_count'] == 3
        assert item['evidence_class'] == 'repeated'
        assert item['status'] == 'pending'
        rejected = client.post(f'/api/cognitive/observations/{observation_id}/feedback?persona_id=anatomy', json={'rating': 'disagree', 'explanation': '这只发生在一次特殊事件中'})
        assert rejected.status_code == 200
        assert client.get('/api/cognitive/report').json()['sections'][2]['observations'] == []
        other = client.post('/api/cognitive/observe', json={'content': text, 'persona_id': 'felix'})
        assert other.json()['candidates'] == []
        paraphrase = client.post('/api/cognitive/observe', json={'content': '我感到焦虑，尤其是在等待重要回复的时候。', 'persona_id': 'debate'})
        assert paraphrase.json()['candidates'] == []


def test_unified_profile_report_history_exclusion_and_clear(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    with TestClient(app) as client:
        conversation = client.post('/api/conversations', json={'mode': 'debate'}).json()
        first = client.post('/api/cognitive/entries', json={'dimension': 'thinking', 'statement': '我习惯先检查论据再作判断。', 'context_note': '讨论公共议题时'})
        assert first.status_code == 200
        view = client.get('/api/cognitive/unified-profile').json()
        assert view['summary']['confirmed_count'] == 1
        assert view['summary']['covered_dimensions'] == ['thinking']
        assert view['dimensions']['thinking'][0]['persona_id'] == 'profile'
        report = client.get('/api/cognitive/report').json()
        assert len(report['sections']) == 10
        assert report['sections'][1]['observations'][0]['evidence'][0]['evidence'] == '我习惯先检查论据再作判断。'
        assert report['sections'][0]['status'] == '信息不足，暂时无法形成判断'
        assert report['question_note']
        excluded = client.post('/api/cognitive/exclusions', json={'topic': '私人工作'}).json()
        assert client.post('/api/cognitive/observe', json={'content': '我喜欢私人工作相关的话题。', 'persona_id': 'felix'}).json()['candidates'] == []
        assert client.delete('/api/cognitive/exclusions/' + excluded['id']).status_code == 200
        earlier = client.post('/api/cognitive/unified-snapshots').json()['id']
        client.post('/api/cognitive/entries', json={'dimension': 'values', 'statement': '我非常重视自主选择的空间。'})
        later = client.post('/api/cognitive/unified-snapshots').json()['id']
        difference = client.get(f'/api/cognitive/unified-snapshots/compare?first_id={earlier}&second_id={later}').json()
        assert difference['changes'][0]['dimension'] == 'values'
        client.post('/api/cognitive/exclusions', json={'topic': '家庭住址'})
        backup = client.get('/api/cognitive/export').json()
        assert backup['data']['cognitive_exclusions'][0]['topic'] == '家庭住址'
        assert client.delete('/api/cognitive/unified-profile').json()['cleared']
        assert client.get('/api/cognitive/unified-profile').json()['summary']['confirmed_count'] == 0
        assert client.get('/api/conversations/' + conversation['id']).status_code == 200
        assert client.post('/api/cognitive/restore', json=backup).status_code == 200
        assert client.get('/api/cognitive/unified-profile').json()['summary']['confirmed_count'] == 2
        assert client.get('/api/cognitive/unified-profile').json()['exclusions'][0]['topic'] == '家庭住址'


def test_active_exploration_uses_selected_persona_only_and_does_not_save(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    captured = []
    async def retrieve(query, context):
        captured.append(('knowledge', context.persona_id))
        return [], 'empty'
    async def complete(config, messages):
        captured.append(('model', config['id'], messages))
        return '请先区分事实和解释。'
    monkeypatch.setattr(main_module.model_config, 'resolve', lambda context: {'id': getattr(context, 'persona_id', context)})
    monkeypatch.setattr(main_module.model_config, 'record_usage', lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.knowledge, 'retrieve', retrieve)
    monkeypatch.setattr(main_module.llm, 'complete_chat', complete)
    with TestClient(app) as client:
        client.post('/api/cognitive/entries', json={'dimension': 'thinking', 'statement': '我习惯先检查论据再作判断。'})
        with connect() as db:
            db.execute("INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES('debate-own','thinking','我会先寻找反例。','confirmed','user_report','debate','local')")
        result = client.post('/api/cognitive/explore', json={'dimension': 'thinking', 'question': '我怎样判断证据？', 'persona_id': 'debate'})
        assert result.status_code == 200
        assert result.json()['saved'] is False
        assert captured[0] == ('knowledge', 'debate')
        assert captured[1][1] == 'debate'
        assert '我习惯先检查论据' not in captured[1][2][1]['content']
        assert '我会先寻找反例' in captured[1][2][1]['content']
        assert client.get('/api/cognitive/unified-profile').json()['summary']['confirmed_count'] == 2


def test_profile_sharing_is_opt_in_per_persona_for_chat_and_exploration(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    captured = []

    async def retrieve(query, context):
        return [], 'empty'

    async def complete(config, messages):
        captured.append((config['id'], messages))
        return '分析完成'

    async def stream(config, messages, usage_callback):
        captured.append((config['id'], messages))
        yield '回应完成'

    monkeypatch.setattr(main_module.model_config, 'resolve', lambda context: {'id': getattr(context, 'persona_id', context)})
    monkeypatch.setattr(main_module.model_config, 'record_usage', lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.knowledge, 'retrieve', retrieve)
    monkeypatch.setattr(main_module.llm, 'complete_chat', complete)
    monkeypatch.setattr(main_module.llm, 'stream_chat', stream)
    monkeypatch.setattr(main_module, 'record_cognitive_observation', lambda *_: None)

    personas = ('anatomy', 'debate', 'guidance', 'self_exploration', 'lucien', 'felix')
    shared = '我习惯先检查资料再作判断。'

    def context_text():
        return '\n'.join(message['content'] for message in captured[-1][1][1:])

    with TestClient(app) as client:
        assert client.post('/api/cognitive/entries', json={'dimension': 'thinking', 'statement': shared}).status_code == 200
        with connect() as db:
            for persona in personas:
                db.execute(
                    "INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES(?,?,?,?,?,?,?)",
                    (f'private-{persona}', 'thinking', f'{persona} 独有的确认观察', 'confirmed', 'user_report', persona, 'local'),
                )

        for persona in personas:
            conversation = client.post('/api/conversations', json={'mode': persona}).json()
            response = client.post('/api/chat/stream', json={'conversation_id': conversation['id'], 'mode': persona, 'content': '今天聊聊。'})
            assert response.status_code == 200
            assert captured[-1][0] == persona
            assert shared not in context_text()
            assert f'{persona} 独有的确认观察' in context_text()
            for other in personas:
                if other != persona:
                    assert f'{other} 独有的确认观察' not in context_text()

            response = client.post('/api/cognitive/explore', json={'dimension': 'thinking', 'question': '我怎样判断资料？', 'persona_id': persona})
            assert response.status_code == 200
            assert captured[-1][0] == persona
            assert shared not in context_text()
            assert f'{persona} 独有的确认观察' in context_text()

        for persona in personas:
            assert client.put('/api/cognitive/settings', json={f'share_profile_{persona}': True}).status_code == 200
            conversation = client.post('/api/conversations', json={'mode': persona}).json()
            response = client.post('/api/chat/stream', json={'conversation_id': conversation['id'], 'mode': persona, 'content': '继续聊聊。'})
            assert response.status_code == 200
            assert shared in context_text()
            assert f'{persona} 独有的确认观察' in context_text()
            for other in personas:
                if other != persona:
                    assert f'{other} 独有的确认观察' not in context_text()

            response = client.post('/api/cognitive/explore', json={'dimension': 'thinking', 'question': '我怎样判断资料？', 'persona_id': persona})
            assert response.status_code == 200
            assert shared in context_text()
            assert f'{persona} 独有的确认观察' in context_text()
            for other in personas:
                if other != persona:
                    assert f'{other} 独有的确认观察' not in context_text()
            assert client.put('/api/cognitive/settings', json={f'share_profile_{persona}': False}).status_code == 200

        assert all(value != '1' for key, value in client.get('/api/cognitive/settings').json().items() if key.startswith('share_profile_'))


def test_report_synthesis_accepts_only_real_evidence_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('EUNOIA_DATA_DIR', str(tmp_path))
    calls = []

    async def complete(config, messages):
        calls.append((config, messages))
        source = json.loads(messages[1]['content'])
        valid_id = source[1]['observations'][0]['id']
        return json.dumps({'sections': [
            {'dimension': 'thinking', 'analysis': '用户会检查论据，但适用范围待核对。', 'evidence_ids': [valid_id], 'uncertainties': '仅有一条确认记录。'},
            {'dimension': 'emotion', 'analysis': '无依据结论', 'evidence_ids': ['invented'], 'uncertainties': ''},
        ], 'questions': [{'text': '何时会改变这种做法？', 'evidence_ids': [valid_id]}]}, ensure_ascii=False)

    monkeypatch.setattr(main_module.model_config, 'resolve', lambda persona: {'id': persona})
    monkeypatch.setattr(main_module.model_config, 'record_usage', lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.llm, 'complete_chat', complete)
    with TestClient(app) as client:
        client.post('/api/cognitive/entries', json={'dimension': 'thinking', 'statement': '我习惯先检查论据再作判断。'})
        response = client.post('/api/cognitive/report/synthesis', json={'model_persona': 'self_exploration'})
        assert response.status_code == 200
        assert len(response.json()['sections']) == 1
        assert response.json()['sections'][0]['dimension'] == 'thinking'
        assert len(response.json()['questions']) == 1
        assert calls[0][0]['id'] == 'self_exploration'
        assert client.get('/api/cognitive/unified-profile').json()['summary']['confirmed_count'] == 1
