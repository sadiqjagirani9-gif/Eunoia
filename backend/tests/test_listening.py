from fastapi.testclient import TestClient

from app import listening, main as main_module, model_config
from app.db import connect
from app.main import app


def test_haven_is_separate_from_personas_profile_and_council(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    calls = []

    async def fake_stream(config, messages, on_usage=None):
        calls.append(messages)
        yield "我在这里听你说。"

    monkeypatch.setattr(listening.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(listening.model_config, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "record_cognitive_observation", lambda *_: (_ for _ in ()).throw(AssertionError("Haven must not update the profile")))

    with TestClient(app) as client:
        config = model_config.save_config({
            "name": "Haven test", "provider": "Ollama", "base_url": "http://127.0.0.1:11434",
            "model_id": "test-local", "protocol": "ollama", "api_key": "", "parameters": {},
            "headers": {}, "timeout_seconds": 10, "capabilities": {},
        })
        assert client.put("/api/listening/model", json={"config_id": config["id"]}).status_code == 200
        assert client.get("/api/model-configs").json()["personas"] == list(model_config.PERSONAS)
        haven = client.post("/api/listening/conversations").json()
        assert haven["persona_id"] == "haven"
        assert client.post("/api/chat/stream", json={"conversation_id": haven["id"], "mode": "anatomy", "content": "你好"}).status_code == 404
        assert client.get("/api/conversations/" + haven["id"]).status_code == 404
        assert all(row["id"] != haven["id"] for row in client.get("/api/conversations").json())
        assert client.post("/api/persona-council", json={"content": "问题", "participants": ["haven", "anatomy"]}).status_code == 422
        assert client.post("/api/cognitive/observe", json={"content": "我很难过", "persona_id": "haven"}).status_code == 422

        response = client.post("/api/listening/chat/stream", json={"conversation_id": haven["id"], "content": "今天很难过，我不想听建议。"})
        assert response.status_code == 200
        assert "我在这里听你说" in response.text
        assert len(calls) == 1
        assert calls[0][0]["role"] == "system"
        assert "无条件接纳" in calls[0][0]["content"]
        assert "不提供行动方案" in calls[0][0]["content"]
        assert "画像" in calls[0][0]["content"]
        assert "当前消息可能提及明确的人身安全风险" not in calls[0][0]["content"]
        assert len(calls[0]) == 2
        crisis = client.post("/api/listening/chat/stream", json={"conversation_id": haven["id"], "content": "我想自杀，已经有计划。"})
        assert crisis.status_code == 200
        assert "当前消息可能提及明确的人身安全风险" in calls[-1][0]["content"]
        with connect() as db:
            assert db.execute("SELECT COUNT(*) FROM cognitive_observations").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM cognitive_evidence").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM listening_messages WHERE user_id='local'").fetchone()[0] == 4


def test_haven_memory_opt_in_one_message_transfer_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    calls = []

    async def fake_stream(config, messages, on_usage=None):
        calls.append(messages)
        yield "我在听。"

    monkeypatch.setattr(listening.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(listening.model_config, "record_usage", lambda *args, **kwargs: None)

    with TestClient(app) as client:
        config = model_config.save_config({
            "name": "Haven test", "provider": "Ollama", "base_url": "http://127.0.0.1:11434",
            "model_id": "test-local", "protocol": "ollama", "api_key": "", "parameters": {},
            "headers": {}, "timeout_seconds": 10, "capabilities": {},
        })
        client.put("/api/listening/model", json={"config_id": config["id"]})
        conversation = client.post("/api/listening/conversations").json()
        assert client.post("/api/listening/memories", json={"content": "请叫我小雨"}).status_code == 409
        client.put("/api/listening/memories/enabled", json={"enabled": True})
        memory = client.post("/api/listening/memories", json={"content": "请叫我小雨"}).json()
        assert client.get("/api/memories?persona_id=anatomy").json()["items"] == []
        first = client.post("/api/listening/chat/stream", json={"conversation_id": conversation["id"], "content": "我只是想被听见。"})
        assert first.status_code == 200
        assert "请叫我小雨" in str(calls[-1])
        client.put("/api/listening/memories/enabled", json={"enabled": False})
        assert client.post("/api/listening/memories", json={"content": "不能写入"}).status_code == 409
        second = client.post("/api/listening/chat/stream", json={"conversation_id": conversation["id"], "content": "这件事请不要告诉别人。"})
        assert second.status_code == 200
        assert "请叫我小雨" not in str(calls[-1])
        assert client.get("/api/listening/memories").json()[0]["id"] == memory["id"]

        history = client.get("/api/listening/conversations/" + conversation["id"]).json()["messages"]
        selected = next(item for item in history if item["content"] == "我只是想被听见。")
        other = next(item for item in history if item["content"] == "这件事请不要告诉别人。")
        assert client.post("/api/listening/transfer", json={"conversation_id": conversation["id"], "message_id": selected["id"], "recipient": "haven"}).status_code == 422
        result = client.post("/api/listening/transfer", json={"conversation_id": conversation["id"], "message_id": selected["id"], "recipient": "anatomy"})
        assert result.status_code == 200
        target = client.get("/api/conversations/" + result.json()["conversation_id"]).json()
        assert target["conversation"]["mode"] == "anatomy"
        assert [item["content"] for item in target["messages"]] == [selected["content"]]
        assert other["content"] not in str(target)
        assert "请叫我小雨" not in str(target)

        with connect() as db:
            db.execute("INSERT INTO listening_conversations(id,user_id,title) VALUES('other-user','someone-else','private')")
            db.execute("INSERT INTO listening_memories(id,user_id,content) VALUES('other-memory','someone-else','private')")
            db.execute("INSERT INTO listening_messages(conversation_id,user_id,role,content) VALUES(?,?,?,?)", (conversation["id"], "someone-else", "user", "other user's private words"))
        assert client.get("/api/listening/conversations/other-user").status_code == 404
        assert client.get("/api/listening/conversations").json()[0]["id"] == conversation["id"]
        assert all(item["id"] != "other-memory" for item in client.get("/api/listening/memories").json())
        assert "other user's private words" not in str(client.get("/api/listening/conversations/" + conversation["id"]).json())
        assert client.delete("/api/listening/history").status_code == 200
        assert client.get("/api/listening/conversations").json() == []
        assert client.get("/api/conversations/" + target["conversation"]["id"]).status_code == 200
        assert client.delete("/api/listening/memories").status_code == 200
        assert client.get("/api/listening/memories").json() == []
