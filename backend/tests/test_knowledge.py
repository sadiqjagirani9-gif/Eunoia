import asyncio
from pathlib import Path

from app.db import init_db
from app import knowledge
from app.persona_context import create_persona_context
from fastapi.testclient import TestClient
from app.main import app


def test_curated_knowledge_is_loaded_and_retrieval_is_persona_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    init_db()
    knowledge.initialize_knowledge()
    monkeypatch.setattr(knowledge, "_embed", lambda texts: _no_embeddings())

    sources = knowledge.list_sources()
    assert len(sources) == 43
    results, method = asyncio.run(knowledge.retrieve("prospect theory loss aversion", create_persona_context("guidance")))
    assert method == "local_lexical"
    assert results
    assert all("/sophia/" in row["source_path"].replace("\\", "/") for row in results)
    wrong_space, _ = asyncio.run(knowledge.retrieve("prospect theory loss aversion", create_persona_context("anatomy")))
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
    assert not (tmp_path / "data" / "knowledge" / "arthur" / "epistemology" / "notes.md").exists()


def test_legacy_imports_are_moved_without_rebuilding_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    legacy_root = tmp_path / "knowledge"
    monkeypatch.setattr(knowledge, "KNOWLEDGE_ROOT", legacy_root)
    init_db()
    legacy_file = legacy_root / "arthur" / "epistemology" / "legacy.md"
    legacy_file.parent.mkdir(parents=True)
    content = "# Legacy evidence\n\nA saved user document."
    legacy_file.write_text(content, encoding="utf-8")
    source_id = knowledge._store_source(str(legacy_file.resolve()), "arthur", "epistemology", "legacy.md", content, "imported")
    with knowledge.connect() as db:
        old_chunks = [tuple(row) for row in db.execute("SELECT id,content FROM knowledge_chunks WHERE source_id=?", (source_id,))]
        db.execute("UPDATE knowledge_chunks SET embedding_json='[0.1,0.2]' WHERE source_id=?", (source_id,))

    knowledge.initialize_knowledge()
    migrated = next(source for source in knowledge.list_sources() if source["id"] == source_id)
    migrated_path = Path(migrated["source_path"])
    assert migrated_path.is_file()
    assert migrated_path.is_relative_to(tmp_path / "data" / "knowledge")
    assert migrated_path.read_text(encoding="utf-8") == content
    assert not legacy_file.exists()
    with knowledge.connect() as db:
        new_chunks = [tuple(row) for row in db.execute("SELECT id,content FROM knowledge_chunks WHERE source_id=?", (source_id,))]
        embedding = db.execute("SELECT embedding_json FROM knowledge_chunks WHERE source_id=?", (source_id,)).fetchone()[0]
    assert new_chunks == old_chunks
    assert embedding == "[0.1,0.2]"
    knowledge.initialize_knowledge()
    assert next(source for source in knowledge.list_sources() if source["id"] == source_id)["source_path"] == str(migrated_path.resolve())


def test_domain_catalog_keeps_spaces_separate():
    assert set(knowledge.PERSONA_DOMAINS.values()) == {"evelyn", "arthur", "sophia", "iris", "lucien", "felix"}
    assert len(knowledge.DOMAIN_LABELS) == 6
    assert all(len(domains) == 7 for persona, domains in knowledge.DOMAIN_LABELS.items() if persona in {"evelyn", "arthur", "sophia", "iris"})
    assert knowledge.DOMAIN_LABELS["lucien"] == {"literature", "poetry", "art_history", "visual_arts", "music", "film_drama", "aesthetics"}
    assert knowledge.DOMAIN_LABELS["felix"] == {"humor_theory", "linguistics", "internet_culture", "popular_culture", "games_entertainment", "social_psychology", "daily_knowledge", "conversation_cases"}


def test_each_seed_document_has_the_required_evidence_fields():
    documents = list(knowledge.KNOWLEDGE_ROOT.glob("*/*/*.md"))
    assert len(documents) == 43
    required = [f"## {index}." for index in range(1, 13)]
    assert all(all(marker in path.read_text(encoding="utf-8") for marker in required) for path in documents)
    for path in documents:
        if path.parts[-3] in {"lucien", "felix"}:
            metadata = knowledge._source_metadata(path)
            assert metadata.get("creator")
            assert metadata.get("discipline")
            assert metadata.get("license")
            assert metadata.get("summary")
            assert metadata.get("scope")


def test_lucien_and_felix_retrieval_uses_only_their_own_knowledge(tmp_path, monkeypatch):
    monkeypatch.setenv("EUNOIA_DATA_DIR", str(tmp_path / "data"))
    init_db()
    knowledge.initialize_knowledge()
    monkeypatch.setattr(knowledge, "_embed", lambda texts: _no_embeddings())
    lucien, _ = asyncio.run(knowledge.retrieve("叙事学 叙述视角 文学", create_persona_context("lucien")))
    felix, _ = asyncio.run(knowledge.retrieve("模因传播 互联网文化", create_persona_context("felix")))
    assert lucien and all("/lucien/" in row["source_path"].replace("\\", "/") for row in lucien)
    assert felix and all("/felix/" in row["source_path"].replace("\\", "/") for row in felix)
    lucien_for_meme, _ = asyncio.run(knowledge.retrieve("网络模因 internet memes", create_persona_context("lucien")))
    felix_for_poetry, _ = asyncio.run(knowledge.retrieve("诗歌理论 韵律", create_persona_context("felix")))
    assert all("/lucien/" in row["source_path"].replace("\\", "/") for row in lucien_for_meme)
    assert all("/felix/" in row["source_path"].replace("\\", "/") for row in felix_for_poetry)


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
        detail = client.get(f"/api/knowledge/sources/{source_id}")
        assert detail.status_code == 200
        assert detail.json()["source"]["content"].startswith("# Evidence")
        updated = client.put(f"/api/knowledge/sources/{source_id}", json={
            "content": "# Evidence\n\nUpdated claim evidence and defeater check.",
            "metadata": {"creator": "Local test", "source_url": "https://example.org/source", "discipline": "epistemology", "license": "test", "summary": "updated", "scope": "test"},
        })
        assert updated.status_code == 200
        assert updated.json()["source"]["creator"] == "Local test"
        updated_search = client.post("/api/knowledge/search", json={"mode": "debate", "query": "Updated claim evidence defeater"})
        assert updated_search.json()["results"][0]["content"].startswith("Updated claim")
        hits = client.get("/api/knowledge/hits?persona=arthur")
        assert hits.status_code == 200 and len(hits.json()["hits"]) >= 2
        assert client.post("/api/knowledge/reindex").json()["method"] == "local_lexical"
        assert client.delete(f"/api/knowledge/sources/{source_id}").json()["deleted"] is True
        assert not (tmp_path / "data" / "knowledge" / "arthur" / "epistemology" / "test-notes.md").exists()
