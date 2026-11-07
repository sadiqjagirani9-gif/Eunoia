import json
from fastapi.testclient import TestClient

from app import main as main_module, model_config
from app.main import app
from app.personas import system_prompt_for


def test_local_conversation_and_memory_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        created = client.post("/api/conversations", json={"mode": "vent"})
        assert created.status_code == 200
        conversation_id = created.json()["id"]
        assert created.json()["mode"] == "anatomy"
        assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []
        assert client.put(f"/api/conversations/{conversation_id}/favorite", json={"enabled": True}).json()["favorite"] is True
        assert client.get("/api/conversations").json()[0]["favorite"] == 1
        assert client.put(f"/api/conversations/{conversation_id}/favorite", json={"enabled": False}).json()["favorite"] is False

        memory = client.post("/api/memories", json={"category": "价值观", "content": "重视坦诚沟通", "kind": "self_report", "confidence": 0.9})
        assert memory.status_code == 200
        memory_id = memory.json()["id"]
        assert client.get("/api/memories").json()["items"][0]["content"] == "重视坦诚沟通"
        assert client.patch(f"/api/memories/{memory_id}", json={"category": "价值观", "content": "重视坦诚和空间", "kind": "self_report", "confidence": 0.8}).status_code == 200
        assert client.delete(f"/api/memories/{memory_id}").json()["deleted"] is True
        assert client.put("/api/memories/enabled?persona_id=anatomy", json={"enabled": True}).json()["enabled"] is True

        assert client.delete(f"/api/conversations/{conversation_id}").json()["deleted"] is True
        assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_cognitive_observe_rejects_foreign_or_missing_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        conversation = client.post("/api/conversations", json={"mode": "felix"}).json()
        mismatched = client.post("/api/cognitive/observe", json={
            "content": "我经常陷入反复思考", "persona_id": "anatomy", "conversation_id": conversation["id"],
        })
        missing = client.post("/api/cognitive/observe", json={
            "content": "我经常陷入反复思考", "persona_id": "felix", "conversation_id": "missing-conversation",
        })
        assert mismatched.status_code == 409
        assert missing.status_code == 404
        with main_module.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM cognitive_observations").fetchone()[0] == 0


def test_relationship_graph_and_timeline_are_persona_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        evelyn = client.put("/api/advanced/graph?persona_id=anatomy", json={
            "people": [{"id": "e-person-a", "name": "甲"}, {"id": "e-person-b", "name": "乙"}],
            "relationships": [{"source_id": "e-person-a", "target_id": "e-person-b", "kind": "朋友", "direction": "directed"}],
        })
        assert evelyn.status_code == 200
        relationship_id = evelyn.json()["relationships"][0]["id"]
        event = client.post("/api/advanced/graph/events?persona_id=anatomy", json={
            "relationship_id": relationship_id, "summary": "发生重要对话", "source_type": "user_report",
        })
        assert event.status_code == 200
        assert len(client.get("/api/advanced/graph?persona_id=anatomy").json()["events"]) == 1
        felix_graph = client.get("/api/advanced/graph?persona_id=felix").json()
        assert [person["id"] for person in felix_graph["people"]] == ["user:felix"]
        assert felix_graph["relationships"] == felix_graph["events"] == []
        assert client.get("/api/advanced/graph/timeline?persona_id=felix").json()["events"] == []
        denied = client.post("/api/advanced/graph/events?persona_id=felix", json={
            "relationship_id": relationship_id, "summary": "跨人格写入", "source_type": "user_report",
        })
        assert denied.status_code == 404


def test_persona_council_is_explicit_and_uses_independent_contexts(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    calls = []

    async def retrieve(query, context):
        return ([{"title": context.persona_id, "content": f"knowledge:{context.persona_id}", "domain": "test", "heading": "test", "source_type": "test", "source_path": context.persona_id}], "local_lexical")

    async def complete(config, messages):
        calls.append((config, messages))
        return f"analysis:{config['id']}"

    monkeypatch.setattr(main_module.knowledge, "retrieve", retrieve)
    monkeypatch.setattr(main_module.model_config, "resolve", lambda persona: {"id": persona.persona_id if hasattr(persona, "persona_id") else persona})
    monkeypatch.setattr(main_module.llm, "complete_chat", complete)
    with TestClient(app) as client:
        response = client.post("/api/persona-council", json={
            "content": "请分析这个选择", "participants": ["anatomy", "lucien"],
        })
        assert response.status_code == 200
        assert [item["persona_id"] for item in response.json()["results"]] == ["anatomy", "lucien"]
        prompts = [item[1][0]["content"] for item in calls]
        assert prompts[0].startswith(system_prompt_for("anatomy"))
        assert prompts[1].startswith(system_prompt_for("lucien"))
        assert all('knowledge:' not in prompt for prompt in prompts)
        contexts = [item[1][1]["content"] for item in calls]
        assert "knowledge:anatomy" in contexts[0] and "knowledge:lucien" not in contexts[0]
        assert "knowledge:lucien" in contexts[1] and "knowledge:anatomy" not in contexts[1]
        assert [len(item[1]) for item in calls] == [3, 3, 2]
        assert '联合会诊的汇总模块' in prompts[2]
        assert 'analysis:anatomy' in contexts[2] and 'analysis:lucien' in contexts[2]
        assert response.json()['summary'] == 'analysis:anatomy'
        assert client.post("/api/persona-council", json={"content": "x", "participants": ["anatomy", "anatomy"]}).status_code == 422
        assert client.get("/api/conversations").json() == []


def test_cognitive_clear_and_restore_keep_persona_ownership(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        with main_module.connect() as db:
            for observation_id, persona in (("evelyn-observation", "anatomy"), ("felix-observation", "felix")):
                db.execute("INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,persona_id,user_id) VALUES(?,?,?,?,?,?,?)", (observation_id, "emotion", persona, "confirmed", "user_report", persona, "local"))
        backup = client.get("/api/cognitive/export").json()
        clear = client.delete("/api/cognitive/profile?persona_id=anatomy")
        assert clear.status_code == 200
        assert client.get("/api/cognitive/profile?persona_id=anatomy").json()["all_observations"] == []
        assert len(client.get("/api/cognitive/profile?persona_id=felix").json()["all_observations"]) == 1
        restored = client.post("/api/cognitive/restore", json=backup)
        assert restored.status_code == 200
        anatomy = client.get("/api/cognitive/profile?persona_id=anatomy").json()["all_observations"]
        felix = client.get("/api/cognitive/profile?persona_id=felix").json()["all_observations"]
        assert [row["id"] for row in anatomy] == ["evelyn-observation"]
        assert [row["id"] for row in felix] == ["felix-observation"]
        assert client.post("/api/cognitive/restore", json=backup).json()["counts"]["cognitive_observations"] == 0


def test_lucien_and_felix_chat_use_their_own_prompts_and_keep_histories_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    captured = []

    class FakeResponse:
        status_code = 200

        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "本地回复"}})

        def raise_for_status(self):
            return None

    class StreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def stream(self, method, url, **kwargs):
            captured.append(kwargs["json"])
            return StreamContext()

    async def no_references(query, mode):
        return [], "empty"

    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(main_module.knowledge, "retrieve", no_references)
    monkeypatch.setattr(main_module, "record_cognitive_observation", lambda *_: None)
    with TestClient(app) as client:
        local_config = model_config.save_config({
            "name": "Fake local model", "provider": "Ollama", "base_url": "http://127.0.0.1:11434",
            "model_id": "test-local", "protocol": "ollama", "api_key": "", "parameters": {},
            "headers": {}, "timeout_seconds": 10, "capabilities": {},
        })
        model_config.assign("lucien", local_config["id"])
        model_config.assign("felix", local_config["id"])
        saved = client.post("/api/memories", json={"category": "偏好", "content": "喜欢轻松交流", "kind": "self_report", "persona_id": "lucien"})
        assert saved.status_code == 200
        client.put("/api/memories/enabled?persona_id=lucien", json={"enabled": True})
        ids = {}
        for mode, persona_name in (("lucien", "文学艺术探索者 Lucien"), ("felix", "日常陪伴者 Felix")):
            conversation = client.post("/api/conversations", json={"mode": mode}).json()
            ids[mode] = conversation["id"]
            wrong_mode = "felix" if mode == "lucien" else "lucien"
            rejected = client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "mode": wrong_mode, "content": "不要写入的内容"})
            assert rejected.status_code == 409
            response = client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "mode": mode, "content": "聊聊今天"})
            assert response.status_code == 200
            assert "本地回复" in response.text
            system_prompt = captured[-1]["messages"][0]["content"]
            assert persona_name in system_prompt
            context_text = "\n".join(message["content"] for message in captured[-1]["messages"][1:])
            if mode == "lucien":
                assert "喜欢轻松交流" in context_text
            else:
                assert "喜欢轻松交流" not in context_text
            assert "喜欢轻松交流" not in system_prompt
            assert ("你是 Eunoia 的日常陪伴者 Felix" not in system_prompt) if mode == "lucien" else ("你是 Eunoia 的文学艺术探索者 Lucien" not in system_prompt)
        for mode, conversation_id in ids.items():
            history = client.get(f"/api/conversations/{conversation_id}").json()
            assert history["conversation"]["mode"] == mode
            assert [message["content"] for message in history["messages"]] == ["聊聊今天", "本地回复"]
            with main_module.connect() as db:
                emotion = db.execute("SELECT person_id,persona_id FROM emotional_states WHERE conversation_id=?", (conversation_id,)).fetchone()
            assert tuple(emotion) == (f"user:{mode}", mode)
        assert client.get("/api/memories?persona_id=lucien").json()["items"][0]["id"] == saved.json()["id"]
        assert all(item["id"] != saved.json()["id"] for item in client.get("/api/memories?persona_id=felix").json()["items"])
