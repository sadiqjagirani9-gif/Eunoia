from fastapi.testclient import TestClient

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
