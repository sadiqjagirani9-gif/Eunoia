"""Additive local backup restore with explicit persona ownership checks."""

import sqlite3

from ..db import connect
from ..persona_context import LOCAL_USER_ID
from ..personas import SPACE_PROMPTS, normalize_mode

RESTORE_ORDER = (
    "conversations", "messages", "memories", "people", "relationships",
    "important_events", "relationship_events", "emotional_states",
    "counterfactual_cases", "simulation_branches", "analysis_reports",
    "cognitive_observations", "cognitive_evidence", "cognitive_feedback",
    "cognitive_snapshots", "cognitive_evolution", "cognitive_contradictions",
    "cognitive_rejections", "cognitive_exclusions",
    "short_term_memories",
)
SCOPED = {
    "conversations", "memories", "people", "relationships", "important_events",
    "relationship_events", "emotional_states", "counterfactual_cases", "analysis_reports",
    "cognitive_observations", "cognitive_snapshots", "cognitive_evolution",
    "cognitive_contradictions",
}
CONVERSATION_LINKED = {
    "important_events", "relationship_events", "emotional_states", "counterfactual_cases",
    "analysis_reports", "cognitive_observations",
}


def _owner(db: sqlite3.Connection, table: str, item_id: str | None) -> str | None:
    if not item_id:
        return None
    row = db.execute(f"SELECT persona_id FROM {table} WHERE id=? AND user_id=?", (item_id, LOCAL_USER_ID)).fetchone()
    return row[0] if row else None


def _conversation_owner(db: sqlite3.Connection, conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    row = db.execute("SELECT mode FROM conversations WHERE id=? AND user_id=?", (conversation_id, LOCAL_USER_ID)).fetchone()
    return normalize_mode(row[0]) if row else None


def _compatible(db: sqlite3.Connection, table: str, row: dict, persona: str) -> bool:
    if table in CONVERSATION_LINKED:
        conversation_id = row.get("source_conversation_id") if table == "cognitive_observations" else row.get("conversation_id")
        if conversation_id and _conversation_owner(db, conversation_id) != persona:
            return False
    if table == "messages" or table == "short_term_memories":
        return _conversation_owner(db, row.get("conversation_id")) is not None
    if table == "cognitive_evidence":
        owner = _owner(db, "cognitive_observations", row.get("observation_id"))
        return owner is not None and (not row.get("conversation_id") or _conversation_owner(db, row["conversation_id"]) == owner)
    if table == "cognitive_feedback":
        return _owner(db, "cognitive_observations", row.get("observation_id")) is not None
    if table == "relationships":
        return all(_owner(db, "people", row.get(key)) == persona for key in ("source_id", "target_id"))
    if table == "relationship_events":
        return all(not row.get(key) or _owner(db, parent, row[key]) == persona for key, parent in (("relationship_id", "relationships"), ("person_id", "people"), ("event_id", "important_events")))
    if table == "emotional_states":
        return all(not row.get(key) or _owner(db, parent, row[key]) == persona for key, parent in (("person_id", "people"), ("event_id", "important_events")))
    if table == "simulation_branches":
        return _owner(db, "counterfactual_cases", row.get("case_id")) is not None
    if table == "cognitive_contradictions" and row.get("observation_id"):
        return _owner(db, "cognitive_observations", row["observation_id"]) == persona
    return True


def restore_backup(data: dict) -> dict:
    restored: dict[str, int] = {}
    with connect() as db:
        for table in RESTORE_ORDER:
            columns = {column[1] for column in db.execute(f"PRAGMA table_info({table})")}
            count = 0
            for source in data.get(table, []):
                if not isinstance(source, dict) or source.get("user_id", LOCAL_USER_ID) != LOCAL_USER_ID:
                    continue
                row = {key: value for key, value in source.items() if key in columns}
                if table == "conversations":
                    if row.get("mode") not in SPACE_PROMPTS and row.get("mode") not in {"reflect", "relationship", "simulation", "vent", "self"}:
                        continue
                    row["mode"] = normalize_mode(row["mode"])
                persona = row.get("persona_id", "unassigned")
                if table in SCOPED:
                    conversation_id = row.get("source_conversation_id") if table == "cognitive_observations" else row.get("conversation_id")
                    conversation_owner = _conversation_owner(db, conversation_id)
                    if conversation_id and not conversation_owner:
                        continue
                    if conversation_owner and persona not in {"unassigned", conversation_owner}:
                        continue
                    persona = conversation_owner or persona
                    if persona not in SPACE_PROMPTS and persona not in {"unassigned", "profile"}:
                        continue
                    if table != "conversations":
                        row["persona_id"] = persona
                    row["user_id"] = LOCAL_USER_ID
                if not row or not _compatible(db, table, row, persona):
                    continue
                names = tuple(row)
                placeholders = ",".join("?" for _ in names)
                sql = f"INSERT OR IGNORE INTO {table}({','.join(names)}) VALUES({placeholders})"
                try:
                    count += db.execute(sql, tuple(row.values())).rowcount
                except (sqlite3.IntegrityError, sqlite3.OperationalError):
                    continue
            restored[table] = count
    return {"restored": True, "counts": restored}
