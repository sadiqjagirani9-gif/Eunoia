"""Local, persona-scoped retrieval augmented generation for curated knowledge."""
import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import uuid
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .db import connect, database_path
from .persona_context import LOCAL_USER_ID, PersonaContext

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"


def import_root() -> Path:
    return database_path().parent / "knowledge"


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = os.environ.get("EUNOIA_EMBEDDING_MODEL", "nomic-embed-text")
PERSONA_DOMAINS = {
    "anatomy": "evelyn",
    "debate": "arthur",
    "guidance": "sophia",
    "self_exploration": "iris",
    "lucien": "lucien",
    "felix": "felix",
}
DOMAIN_LABELS = {
    "evelyn": {"general_psychology", "psychoanalysis", "emotion_psychology", "attachment_theory", "social_psychology", "relationship_psychology", "cognitive_behavioral_theory"},
    "arthur": {"formal_logic", "informal_logic", "epistemology", "philosophy_of_science", "ethics", "political_philosophy", "philosophy_history"},
    "sophia": {"behavioral_science", "behavioral_economics", "decision_theory", "sociology", "management", "educational_psychology", "career_development"},
    "iris": {"personality_psychology", "cognitive_science", "developmental_psychology", "self_identity", "existentialism", "phenomenology", "self_determination_theory"},
    "lucien": {"literature", "poetry", "art_history", "visual_arts", "music", "film_drama", "aesthetics"},
    "felix": {"humor_theory", "linguistics", "internet_culture", "popular_culture", "games_entertainment", "social_psychology", "daily_knowledge", "conversation_cases"},
}
HAVEN_DOMAIN_LABELS = {"rhetoric", "sarcasm", "sharp_tongue", "profanity_pragmatics", "logic_rebuttal", "humor", "internet_language", "conflict_communication", "response_templates", "style_profiles", "context_intensity", "quality_control"}
HAVEN_EMOTIONAL_DOMAIN_LABELS = {
    "emotion_psychology", "emotion_comfort", "life_difficulties", "empathy", "comfort_language",
    "acceptance", "companionship", "comfort_taboo", "needs_recognition", "relationship_support",
    "self_compassion", "loss_grief", "existential_support", "stress_regulation", "crisis_boundaries",
}


def domains_for(persona: str) -> set[str]:
    """Return catalog domains without registering Haven as a normal persona."""
    if persona == "haven":
        return HAVEN_DOMAIN_LABELS
    if persona == "haven_emotional_support":
        return HAVEN_EMOTIONAL_DOMAIN_LABELS
    return DOMAIN_LABELS.get(persona, set())


def all_domains() -> dict[str, set[str]]:
    return {**DOMAIN_LABELS, "haven": HAVEN_DOMAIN_LABELS, "haven_emotional_support": HAVEN_EMOTIONAL_DOMAIN_LABELS}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunks(text: str, limit: int = 1500) -> list[tuple[str, str]]:
    heading = "知识条目"
    result: list[tuple[str, str]] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        if line.startswith("#"):
            if current:
                result.append((heading, "\n".join(current).strip()))
                current, size = [], 0
            heading = line.lstrip("# ").strip() or heading
            continue
        if current and size + len(line) > limit:
            result.append((heading, "\n".join(current).strip()))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        result.append((heading, "\n".join(current).strip()))
    return [(h, c) for h, c in result if c]


def _source_meta(path: Path) -> tuple[str, str, str]:
    relative = path.resolve().relative_to(KNOWLEDGE_ROOT.resolve())
    persona = relative.parts[0]
    domain = relative.parts[1] if len(relative.parts) > 2 else "general"
    title = next((line.lstrip("# ").strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("#")), path.stem)
    return persona, domain, title


METADATA_FIELDS = ("creator", "source_url", "discipline", "published", "source_version", "license", "summary", "scope", "notes")


def _source_metadata(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".meta.json")
    if not sidecar.is_file():
        return {}
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return {field: str(data.get(field, "")) for field in METADATA_FIELDS}


def _store_source(source_path: str, persona: str, domain: str, title: str, content: str, source_type: str, metadata: dict | None = None, user_id: str = LOCAL_USER_ID) -> str:
    if not content.strip():
        raise ValueError("知识内容不能为空")
    checksum = _digest(content)
    with connect() as db:
        old = db.execute("SELECT id,checksum FROM knowledge_sources WHERE source_path=?", (source_path,)).fetchone()
        source_id = old["id"] if old else str(uuid.uuid4())
        if old and old["checksum"] == checksum:
            if metadata is not None:
                values = {field: str(metadata.get(field, "")) for field in METADATA_FIELDS}
                db.execute("INSERT INTO knowledge_source_metadata(source_id,creator,source_url,discipline,published,source_version,license,summary,scope,notes) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET creator=excluded.creator,source_url=excluded.source_url,discipline=excluded.discipline,published=excluded.published,source_version=excluded.source_version,license=excluded.license,summary=excluded.summary,scope=excluded.scope,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP", (source_id, *(values[field] for field in METADATA_FIELDS)))
            return source_id
        db.execute("INSERT INTO knowledge_sources(id,user_id,persona,domain,title,source_path,source_type,content,checksum) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(source_path) DO UPDATE SET user_id=excluded.user_id,persona=excluded.persona,domain=excluded.domain,title=excluded.title,source_type=excluded.source_type,content=excluded.content,checksum=excluded.checksum,updated_at=CURRENT_TIMESTAMP", (source_id, user_id, persona, domain, title, source_path, source_type, content, checksum))
        if metadata is not None:
            values = {field: str(metadata.get(field, "")) for field in METADATA_FIELDS}
            db.execute("INSERT INTO knowledge_source_metadata(source_id,creator,source_url,discipline,published,source_version,license,summary,scope,notes) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET creator=excluded.creator,source_url=excluded.source_url,discipline=excluded.discipline,published=excluded.published,source_version=excluded.source_version,license=excluded.license,summary=excluded.summary,scope=excluded.scope,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP", (source_id, *(values[field] for field in METADATA_FIELDS)))
        db.execute("DELETE FROM knowledge_chunks WHERE source_id=?", (source_id,))
        for heading, chunk in _chunks(content):
            db.execute("INSERT INTO knowledge_chunks(id,source_id,user_id,persona,domain,heading,content) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), source_id, user_id, persona, domain, heading, chunk))
    return source_id


def initialize_knowledge() -> None:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
    private_root = import_root().resolve()
    legacy_root = KNOWLEDGE_ROOT.resolve()
    moved_files: list[Path] = []
    with connect() as db:
        imported = db.execute(
            "SELECT id,persona,domain,title,source_path,content FROM knowledge_sources WHERE source_type!='curated'"
        ).fetchall()
        for row in imported:
            if row["domain"] not in domains_for(row["persona"]):
                continue
            recorded_path = Path(row["source_path"])
            old_path = recorded_path.resolve()
            if old_path == legacy_root or legacy_root not in old_path.parents or not recorded_path.is_file() or recorded_path.is_symlink():
                continue
            target_dir = (private_root / row["persona"] / row["domain"]).resolve()
            if private_root not in target_dir.parents:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            content = recorded_path.read_text(encoding="utf-8")
            source_key = hashlib.sha256(row["id"].encode("utf-8")).hexdigest()[:16]
            target = target_dir / f"{source_key}_{recorded_path.name}"
            if target.exists() and target.read_text(encoding="utf-8") != content:
                content_key = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
                target = target_dir / f"{source_key}_{content_key}_{recorded_path.name}"
            if private_root not in target.resolve().parents:
                continue
            if target.exists() and target.read_text(encoding="utf-8") != content:
                continue
            if not target.exists():
                temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                temporary.write_text(content, encoding="utf-8")
                temporary.replace(target)
            db.execute("UPDATE knowledge_sources SET source_path=? WHERE id=?", (str(target.resolve()), row["id"]))
            moved_files.append(recorded_path)
    for old_path in moved_files:
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            pass
    indexed_paths = {str(path.resolve()) for path in KNOWLEDGE_ROOT.glob("*/*/*.md")}
    with connect() as db:
        for row in db.execute("SELECT id,source_path FROM knowledge_sources WHERE source_type='curated'").fetchall():
            if row["source_path"] not in indexed_paths:
                db.execute("DELETE FROM knowledge_sources WHERE id=?", (row["id"],))
    with connect() as db:
        db.execute("PRAGMA foreign_keys=ON")
    for path in KNOWLEDGE_ROOT.glob("*/*/*.md"):
        try:
            persona, domain, title = _source_meta(path)
            if domain not in domains_for(persona):
                continue
            _store_source(str(path.resolve()), persona, domain, title, path.read_text(encoding="utf-8"), "curated", _source_metadata(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue


def _terms(text: str) -> list[str]:
    terms: list[str] = []
    for part in re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u3400-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            terms.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
            terms.extend(part)
        else:
            terms.append(part)
    return terms


def _lexical_score(query: str, document: str) -> float:
    q, d = Counter(_terms(query)), Counter(_terms(document))
    if not q or not d:
        return 0.0
    overlap = sum(min(count, d[term]) for term, count in q.items())
    return overlap / math.sqrt(sum(q.values()) * sum(d.values()))


async def _embed(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=2)) as client:
            response = await client.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBEDDING_MODEL, "input": texts})
            response.raise_for_status()
            vectors = response.json().get("embeddings")
        return vectors if isinstance(vectors, list) and len(vectors) == len(texts) else None
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norms = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norms if norms else 0.0


async def reindex() -> dict:
    initialize_knowledge()
    with connect() as db:
        rows = db.execute("SELECT id,content FROM knowledge_chunks ORDER BY id").fetchall()
    vectors: list[list[float]] = []
    for offset in range(0, len(rows), 24):
        batch = await _embed([row["content"] for row in rows[offset:offset + 24]])
        if batch is None:
            vectors = []
            break
        vectors.extend(batch)
    if vectors and len(vectors) == len(rows):
        with connect() as db:
            db.executemany("UPDATE knowledge_chunks SET embedding_json=? WHERE id=?", [(json.dumps(vector), row["id"]) for row, vector in zip(rows, vectors)])
    return {"chunks": len(rows), "embedding_model": EMBEDDING_MODEL if vectors and len(vectors) == len(rows) else None, "method": "ollama_embedding" if vectors and len(vectors) == len(rows) else "local_lexical"}


async def index_source(source_id: str) -> str:
    with connect() as db:
        rows = db.execute("SELECT id,content FROM knowledge_chunks WHERE source_id=? ORDER BY id", (source_id,)).fetchall()
    vectors = await _embed([row["content"] for row in rows])
    if vectors and len(vectors) == len(rows):
        with connect() as db:
            db.executemany("UPDATE knowledge_chunks SET embedding_json=? WHERE id=?", [(json.dumps(vector), row["id"]) for row, vector in zip(rows, vectors)])
        return "ollama_embedding"
    return "local_lexical"


async def retrieve(query: str, context: PersonaContext, limit: int = 5) -> tuple[list[dict], str]:
    mode = context.persona_id
    if context.knowledge_namespace != f"{context.user_id}:{mode}":
        raise ValueError("知识库命名空间与人格上下文不一致")
    persona = PERSONA_DOMAINS.get(mode)
    if not persona:
        return [], "disabled"
    with connect() as db:
        rows = db.execute("SELECT c.id,c.domain,c.heading,c.content,c.embedding_json,s.title,s.source_path,s.source_type FROM knowledge_chunks c JOIN knowledge_sources s ON s.id=c.source_id WHERE c.user_id=? AND s.user_id=? AND c.persona=? AND s.persona=? ORDER BY c.id", (context.user_id, context.user_id, persona, persona)).fetchall()
    if not rows:
        _log_search(context.user_id, mode, persona, query, "empty", [])
        return [], "empty"
    query_vectors = await _embed([query])
    qvector = query_vectors[0] if query_vectors else None
    scored = []
    for row in rows:
        lexical = _lexical_score(query, row["content"] + " " + row["title"] + " " + row["domain"])
        vector = json.loads(row["embedding_json"]) if row["embedding_json"] else None
        semantic = _cosine(qvector, vector) if qvector and vector else None
        score = (0.65 * semantic + 0.35 * lexical) if semantic is not None else lexical
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [{"score": round(score, 4), "domain": row["domain"], "heading": row["heading"], "title": row["title"], "source_path": row["source_path"], "source_type": row["source_type"], "content": row["content"]} for score, row in scored[:limit]]
    method = "ollama_embedding+local_lexical" if qvector and any(row["embedding_json"] for row in rows) else "local_lexical"
    _log_search(context.user_id, mode, persona, query, method, selected)
    return selected, method


async def retrieve_haven_language(query: str, limit: int = 4, user_id: str = LOCAL_USER_ID) -> tuple[list[dict], str]:
    """Retrieve only the curated Haven language namespace.

    This intentionally does not construct a normal PersonaContext: Haven is a
    separate listening space and must never become a seventh analytical persona.
    The SQL predicate pins both source and chunk ownership to the Haven
    namespace, while the caller supplies only the current user id.
    """
    if not query.strip():
        return [], "empty"
    with connect() as db:
        rows = db.execute(
            "SELECT c.id,c.domain,c.heading,c.content,c.embedding_json,s.title,s.source_path,s.source_type "
            "FROM knowledge_chunks c JOIN knowledge_sources s ON s.id=c.source_id "
            "WHERE c.user_id=? AND s.user_id=? AND c.persona='haven' AND s.persona='haven' ORDER BY c.id",
            (user_id, user_id),
        ).fetchall()
    if not rows:
        _log_search(user_id, "haven", "haven", query, "empty", [])
        return [], "empty"
    query_vectors = await _embed([query])
    qvector = query_vectors[0] if query_vectors else None
    scored = []
    for row in rows:
        lexical = _lexical_score(query, row["content"] + " " + row["title"] + " " + row["domain"])
        vector = json.loads(row["embedding_json"]) if row["embedding_json"] else None
        semantic = _cosine(qvector, vector) if qvector and vector else None
        score = (0.65 * semantic + 0.35 * lexical) if semantic is not None else lexical
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [{"score": round(score, 4), "domain": row["domain"], "heading": row["heading"],
                 "title": row["title"], "source_path": row["source_path"],
                 "source_type": row["source_type"], "content": row["content"]}
                for score, row in scored[:limit]]
    method = "ollama_embedding+local_lexical" if qvector and any(row["embedding_json"] for row in rows) else "local_lexical"
    _log_search(user_id, "haven", "haven", query, method, selected)
    return selected, method


async def retrieve_haven_emotional_support(query: str, limit: int = 4, user_id: str = LOCAL_USER_ID) -> tuple[list[dict], str]:
    """Retrieve only Haven's emotional comfort and support namespace."""
    if not query.strip():
        return [], "empty"
    persona = "haven_emotional_support"
    with connect() as db:
        rows = db.execute(
            "SELECT c.id,c.domain,c.heading,c.content,c.embedding_json,s.title,s.source_path,s.source_type "
            "FROM knowledge_chunks c JOIN knowledge_sources s ON s.id=c.source_id "
            "WHERE c.user_id=? AND s.user_id=? AND c.persona=? AND s.persona=? ORDER BY c.id",
            (user_id, user_id, persona, persona),
        ).fetchall()
    if not rows:
        _log_search(user_id, "haven_emotional_support", persona, query, "empty", [])
        return [], "empty"
    query_vectors = await _embed([query])
    qvector = query_vectors[0] if query_vectors else None
    scored = []
    for row in rows:
        lexical = _lexical_score(query, row["content"] + " " + row["title"] + " " + row["domain"])
        vector = json.loads(row["embedding_json"]) if row["embedding_json"] else None
        semantic = _cosine(qvector, vector) if qvector and vector else None
        score = (0.65 * semantic + 0.35 * lexical) if semantic is not None else lexical
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [{"score": round(score, 4), "domain": row["domain"], "heading": row["heading"],
                 "title": row["title"], "source_path": row["source_path"],
                 "source_type": row["source_type"], "content": row["content"]}
                for score, row in scored[:limit]]
    method = "ollama_embedding+local_lexical" if qvector and any(row["embedding_json"] for row in rows) else "local_lexical"
    _log_search(user_id, "haven_emotional_support", persona, query, method, selected)
    return selected, method


def _log_search(user_id: str, mode: str, persona: str, query: str, method: str, hits: list[dict]) -> None:
    compact_hits = [{"title": item["title"], "domain": item["domain"], "score": item["score"]} for item in hits]
    with connect() as db:
        db.execute("INSERT INTO knowledge_search_log(user_id,mode,persona,query,method,hits_json) VALUES(?,?,?,?,?,?)", (user_id, mode, persona, query, method, json.dumps(compact_hits, ensure_ascii=False)))


def list_search_hits(persona: str | None = None, limit: int = 100, user_id: str = LOCAL_USER_ID) -> list[dict]:
    with connect() as db:
        if persona:
            rows = db.execute("SELECT * FROM knowledge_search_log WHERE user_id=? AND persona=? ORDER BY id DESC LIMIT ?", (user_id, persona, limit)).fetchall()
        else:
            rows = db.execute("SELECT * FROM knowledge_search_log WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    result = [dict(row) for row in rows]
    for row in result:
        row["hits"] = json.loads(row.pop("hits_json"))
    return result


def list_sources() -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT s.id,s.persona,s.domain,s.title,s.source_path,s.source_type,s.updated_at,(SELECT COUNT(*) FROM knowledge_chunks c WHERE c.source_id=s.id) chunks,m.creator,m.source_url,m.discipline,m.published,m.source_version,m.license,m.summary,m.scope,m.notes FROM knowledge_sources s LEFT JOIN knowledge_source_metadata m ON m.source_id=s.id ORDER BY s.persona,s.domain,s.title").fetchall()]


def get_source(source_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT s.*,m.creator,m.source_url,m.discipline,m.published,m.source_version,m.license,m.summary,m.scope,m.notes FROM knowledge_sources s LEFT JOIN knowledge_source_metadata m ON m.source_id=s.id WHERE s.id=?", (source_id,)).fetchone()
    return dict(row) if row else None


def update_source(source_id: str, content: str, metadata: dict | None = None) -> dict | None:
    source = get_source(source_id)
    if not source or source["source_type"] == "curated":
        return None
    recorded_path = Path(source["source_path"])
    path = recorded_path.resolve()
    root = import_root().resolve()
    if root not in path.parents or recorded_path.is_symlink():
        raise ValueError("只允许更新本机导入的知识资料")
    if not content.strip():
        raise ValueError("知识内容不能为空")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    _store_source(str(path), source["persona"], source["domain"], source["title"], content, source["source_type"], metadata)
    return get_source(source_id)


def import_text(persona: str, domain: str, name: str, content: str, source_type: str = "imported", metadata: dict | None = None) -> dict:
    if domain not in domains_for(persona):
        raise ValueError("人格或知识领域无效")
    safe_name = re.sub(r"[^\w.\-\u3400-\u9fff]+", "_", Path(name).name).strip("._") or "imported.md"
    folder = import_root() / persona / domain
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name
    if target.suffix.lower() not in {".md", ".txt"}:
        target = target.with_suffix(".md")
    with connect() as db:
        occupied = db.execute("SELECT source_type FROM knowledge_sources WHERE source_path=?", (str(target.resolve()),)).fetchone()
    if target.exists() and occupied and occupied["source_type"] == "curated":
        target = folder / f"imported_{uuid.uuid4().hex[:8]}_{target.name}"
    target.write_text(content, encoding="utf-8")
    source_id = _store_source(str(target.resolve()), persona, domain, safe_name, content, source_type, metadata)
    return next(item for item in list_sources() if item["id"] == source_id)


def delete_source(source_id: str) -> bool:
    with connect() as db:
        row = db.execute("SELECT source_path FROM knowledge_sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            return False
        path = Path(row["source_path"]).resolve()
        managed_root = import_root().resolve()
        with_root = path == managed_root or managed_root in path.parents
        db.execute("DELETE FROM knowledge_sources WHERE id=?", (source_id,))
    if with_root and path.is_file():
        path.unlink()
    return True


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "header"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "header"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


async def fetch_public_webpage(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("网页导入仅允许 HTTPS 地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("不允许访问本机或内网地址")
    except socket.gaierror as exc:
        raise ValueError("无法解析网页地址") from exc
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={"User-Agent": "EunoiaLocalKnowledge/1.0"}) as client:
        response = await client.get(url)
        response.raise_for_status()
    parser = _TextExtractor()
    parser.feed(response.text[:2_000_000])
    return "\n".join(parser.parts)[:100_000]
