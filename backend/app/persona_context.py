"""Server-derived runtime identity and data namespaces for a persona request."""
from dataclasses import dataclass

from .db import connect
from .persona import MODES
from .personas import LEGACY_MODE_MAP, SPACE_PROMPTS, normalize_mode, system_prompt_for

LOCAL_USER_ID = "local"


@dataclass(frozen=True)
class PersonaContext:
    user_id: str
    persona_id: str
    conversation_id: str | None
    system_prompt: str
    memory_namespace: str
    knowledge_namespace: str
    model_config_id: str | None
    allowed_tools: tuple[str, ...]
    permissions: frozenset[str]


def create_persona_context(persona_id: str, conversation_id: str | None = None) -> PersonaContext:
    if persona_id not in SPACE_PROMPTS:
        raise ValueError("人格空间无效")
    if conversation_id:
        with connect() as db:
            conversation = db.execute(
                "SELECT id,mode,user_id FROM conversations WHERE id=?",
                (conversation_id,),
            ).fetchone()
        if not conversation or conversation["user_id"] != LOCAL_USER_ID:
            raise LookupError("对话不存在")
        if normalize_mode(conversation["mode"]) != persona_id:
            raise PermissionError("该对话属于其他人格空间")

    from . import model_config

    config = model_config.resolve(persona_id)
    return PersonaContext(
        user_id=LOCAL_USER_ID,
        persona_id=persona_id,
        conversation_id=conversation_id,
        system_prompt=system_prompt_for(persona_id),
        memory_namespace=f"{LOCAL_USER_ID}:{persona_id}",
        knowledge_namespace=f"{LOCAL_USER_ID}:{persona_id}",
        model_config_id=config["id"] if config else None,
        allowed_tools=(),
        permissions=frozenset({"read_own_memory", "write_own_memory", "read_own_knowledge"}),
    )


def validate_requested_persona(conversation_id: str, requested: str | None) -> PersonaContext:
    with connect() as db:
        conversation = db.execute(
            "SELECT mode,user_id FROM conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
    if not conversation or conversation["user_id"] != LOCAL_USER_ID:
        raise LookupError("对话不存在")
    persona_id = normalize_mode(conversation["mode"])
    if requested is not None:
        if requested not in MODES and requested not in LEGACY_MODE_MAP:
            raise ValueError("人格空间无效")
        if normalize_mode(requested) != persona_id:
            raise PermissionError("请求的人格与该对话所属空间不一致")
    return create_persona_context(persona_id, conversation_id)
