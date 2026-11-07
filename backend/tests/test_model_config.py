import json

import pytest
from fastapi.testclient import TestClient

from app import model_config
from app.db import connect, init_db
from app.main import app
from app.providers.anthropic import AnthropicMessagesAdapter
from app.providers.ollama import OllamaAdapter
from app.providers.openai_compatible import OpenAICompatibleAdapter


def _data(name="Test API", protocol="openai_compatible", base_url="https://api.example.test/v1", model_id="example-chat", api_key="sk-local-test-secret"):
    return {
        "name": name, "provider": "Custom", "base_url": base_url, "model_id": model_id,
        "protocol": protocol, "api_key": api_key, "parameters": {"temperature": 0.4, "max_tokens": 64},
        "headers": {}, "timeout_seconds": 20, "capabilities": {"text_generation": True},
        "input_price_per_million": 1.5, "output_price_per_million": 3.0,
    }


def test_api_key_is_encrypted_and_never_returned(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    init_db()
    config = model_config.save_config(_data())
    assert config["has_api_key"] is True
    assert "api_key" not in config and "api_key_enc" not in config
    with connect() as db:
        stored = db.execute("SELECT api_key_enc FROM model_configs WHERE id=?", (config["id"],)).fetchone()[0]
    assert "sk-local-test-secret" not in stored
    assert model_config.decrypt_secret(stored) == "sk-local-test-secret"
    if model_config.os.name == "nt":
        assert stored.startswith("dpapi:")
    else:
        assert stored.startswith("fernet:")


def test_remote_http_and_sensitive_custom_headers_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    init_db()
    with pytest.raises(ValueError, match="HTTPS"):
        model_config.save_config(_data(base_url="http://api.example.test/v1"))
    with pytest.raises(ValueError, match="敏感字段"):
        model_config.save_config({**_data(), "headers": {"Authorization": "Bearer other"}})


def test_six_personas_bind_independently_and_can_use_global_default(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    init_db()
    first = model_config.save_config(_data(name="A"))
    second = model_config.save_config(_data(name="B", model_id="other-chat", api_key="sk-another-secret"))
    model_config.set_default(first["id"])
    model_config.assign("anatomy", second["id"])
    for persona in model_config.PERSONAS[1:]:
        model_config.assign(persona, None)
    assert model_config.resolve("anatomy")["model_id"] == "other-chat"
    assert model_config.resolve("felix")["model_id"] == "example-chat"
    assert model_config.set_persona_settings("felix", 0.2, 333, False)["max_output_tokens"] == 333
    assert model_config.resolve("felix")["parameters"]["max_tokens"] == 333
    model_config.delete_config(first["id"])
    assert model_config.get_default() is None
    assert model_config.bindings()["felix"] is None
    assert model_config.resolve("felix") is None


def test_api_config_crud_never_returns_secret_and_missing_binding_blocks_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        created = client.post("/api/model-configs", json=_data())
        assert created.status_code == 200
        config = created.json()["config"]
        assert "api_key" not in config and "api_key_enc" not in config
        conversation = client.post("/api/conversations", json={"mode": "anatomy"}).json()
        response = client.post("/api/chat/stream", json={"conversation_id": conversation["id"], "content": "hello"})
        assert response.status_code == 409
        detail = client.get(f"/api/model-configs/{config['id']}")
        assert detail.status_code == 200
        assert "api_key" not in detail.json()["config"]
        assert client.put("/api/persona-models", json={"assignments": {"anatomy": config["id"], "felix": None}}).status_code == 200
        assert client.put("/api/model-default", json={"config_id": config["id"]}).json()["default_config_id"] == config["id"]
        assert client.delete(f"/api/model-configs/{config['id']}").json()["deleted"] is True
        assert client.get("/api/model-configs").json()["configs"] == []


def test_provider_adapters_build_independent_protocol_requests_and_parse_usage():
    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "hi"}]
    openai = OpenAICompatibleAdapter()
    config = _data()
    config.update({"api_key": "secret", "parameters": {"temperature": 0.4, "max_tokens": 55}, "capabilities": {"stream_usage": True}})
    payload = openai.payload(config, messages, True)
    assert openai.endpoint(config) == "https://api.example.test/v1/chat/completions"
    assert openai.headers(config)["Authorization"] == "Bearer secret"
    assert payload["stream_options"]["include_usage"] is True
    token, input_tokens, output_tokens = openai.parse_event('data: ' + json.dumps({"choices": [{"delta": {"content": "x"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}))
    assert (token, input_tokens, output_tokens) == ("x", 3, 1)

    anthropic = AnthropicMessagesAdapter()
    anthropic_payload = anthropic.payload({**config, "base_url": "https://api.anthropic.test", "protocol": "anthropic"}, messages, True)
    assert anthropic_payload["system"] == "system"
    assert "system" not in [message["role"] for message in anthropic_payload["messages"]]
    assert anthropic.endpoint({"base_url": "https://api.anthropic.test", "protocol": "anthropic"}) == "https://api.anthropic.test/v1/messages"
    assert anthropic.parse_event('data: ' + json.dumps({"type": "content_block_delta", "delta": {"text": "a"}}))[0] == "a"

    ollama = OllamaAdapter()
    local = {**config, "base_url": "http://127.0.0.1:11434", "protocol": "ollama", "api_key": "", "model_id": "local:latest"}
    ollama_payload = ollama.payload(local, messages, True)
    assert ollama_payload["options"]["num_predict"] == 55
    assert "Authorization" not in ollama.headers(local)
    assert ollama.parse_event(json.dumps({"message": {"content": "local"}, "prompt_eval_count": 8, "eval_count": 2})) == ("local", 8, 2)
