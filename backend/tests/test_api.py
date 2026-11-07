import json
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app


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
        assert client.put("/api/memories/enabled", json={"enabled": True}).json()["enabled"] is True

        assert client.delete(f"/api/conversations/{conversation_id}").json()["deleted"] is True
        assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_lucien_and_felix_chat_use_their_own_prompts_and_keep_histories_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    captured = []

    class FakeResponse:
        status_code = 200

        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "本地回复"}})

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

        def stream(self, method, url, json):
            captured.append(json)
            return StreamContext()

    async def no_references(query, mode):
        return [], "empty"

    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(main_module.knowledge, "retrieve", no_references)
    monkeypatch.setattr(main_module, "record_cognitive_observation", lambda *_: None)
    with TestClient(app) as client:
        saved = client.post("/api/memories", json={"category": "偏好", "content": "喜欢轻松交流", "kind": "self_report"})
        assert saved.status_code == 200
        client.put("/api/memories/enabled", json={"enabled": True})
        ids = {}
        for mode, wrong_request_mode, persona_name in (("lucien", "felix", "文学艺术探索者 Lucien"), ("felix", "lucien", "日常陪伴者 Felix")):
            conversation = client.post("/api/conversations", json={"mode": mode}).json()
            ids[mode] = conversation["id"]
            response = client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "mode": wrong_request_mode, "content": "聊聊今天"})
            assert response.status_code == 200
            assert "本地回复" in response.text
            system_prompt = captured[-1]["messages"][0]["content"]
            assert persona_name in system_prompt
            assert "喜欢轻松交流" in system_prompt
            assert ("Felix" not in system_prompt) if mode == "lucien" else ("Lucien" not in system_prompt)
        for mode, conversation_id in ids.items():
            history = client.get(f"/api/conversations/{conversation_id}").json()
            assert history["conversation"]["mode"] == mode
            assert [message["content"] for message in history["messages"]] == ["聊聊今天", "本地回复"]
        assert client.get("/api/memories").json()["items"][0]["id"] == saved.json()["id"]
