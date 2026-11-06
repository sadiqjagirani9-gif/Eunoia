import asyncio

from app.db import init_db
from app import knowledge
from fastapi.testclient import TestClient
from app.main import app


def test_curated_knowledge_is_loaded_and_retrieval_is_persona_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    init_db()
    knowledge.initialize_knowledge()
    monkeypatch.setattr(knowledge, "_embed", lambda texts: _no_embeddings())

    sources = knowledge.list_sources()
    assert len(sources) == 28
    results, method = asyncio.run(knowledge.retrieve("prospect theory loss aversion", "guidance"))
    assert method == "local_lexical"
    assert results
    assert all("/sophia/" in row["source_path"].replace("\\", "/") for row in results)
    wrong_space, _ = asyncio.run(knowledge.retrieve("prospect theory loss aversion", "anatomy"))
    assert all("/evelyn/" in row["source_path"].replace("\\", "/") for row in wrong_space)


async def _no_embeddings():
    return None


def test_import_update_and_delete_are_local_and_reindexable(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(knowledge, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    init_db()
    imported = knowledge.import_text("arthur", "epistemology", "notes.md", "# Evidence notes\n\nEvidence and uncertainty.")
    assert imported["source_type"] == "imported"
    knowledge.import_text("arthur", "epistemology", "notes.md", "# Evidence notes\n\nEvidence and counterexamples.")
    assert len(knowledge.list_sources()) == 1
    assert knowledge.delete_source(imported["id"])
    assert knowledge.list_sources() == []
    assert not (tmp_path / "knowledge" / "arthur" / "epistemology" / "notes.md").exists()


def test_domain_catalog_keeps_spaces_separate():
    assert set(knowledge.PERSONA_DOMAINS.values()) == {"evelyn", "arthur", "sophia", "iris"}
    assert len(knowledge.DOMAIN_LABELS) == 4
    assert all(len(domains) == 7 for domains in knowledge.DOMAIN_LABELS.values())


def test_each_seed_document_has_the_required_evidence_fields():
    documents = list(knowledge.KNOWLEDGE_ROOT.glob("*/*/*.md"))
    assert len(documents) == 28
    required = [f"## {index}." for index in range(1, 13)]
    assert all(all(marker in path.read_text(encoding="utf-8") for marker in required) for path in documents)


def test_knowledge_api_import_search_reindex_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(knowledge, "KNOWLEDGE_ROOT", tmp_path / "knowledge")

    async def no_embeddings(texts):
        return None

    monkeypatch.setattr(knowledge, "_embed", no_embeddings)
    with TestClient(app) as client:
        imported = client.post("/api/knowledge/import", json={
            "persona": "arthur", "domain": "epistemology", "name": "test-notes.md",
            "content": "# Evidence\n\nA claim needs relevant evidence and a defeater check.",
        })
        assert imported.status_code == 200
        source_id = imported.json()["source"]["id"]
        search = client.post("/api/knowledge/search", json={"mode": "debate", "query": "evidence defeater claim"})
        assert search.status_code == 200
        assert search.json()["results"][0]["title"] == "test-notes.md"
        assert client.post("/api/knowledge/reindex").json()["method"] == "local_lexical"
        assert client.delete(f"/api/knowledge/sources/{source_id}").json()["deleted"] is True
