"""Incrementally record traceable, revisable cognitive evidence."""
import json
import uuid
from datetime import datetime, timezone

from ..cognitive_engine.confidence_engine import confidence_label
from ..db import connect
from ..persona_context import LOCAL_USER_ID
from .profile_updater import extract_signals, similar


def _days_between(first: str, last: str) -> int:
    try:
        a = datetime.fromisoformat(first.replace('Z', '+00:00'))
        b = datetime.fromisoformat(last.replace('Z', '+00:00'))
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=timezone.utc)
        return (b - a).days
    except (ValueError, AttributeError):
        return 0


def record_candidates(content: str, persona_id: str, conversation_id: str | None, settings: dict) -> list[dict]:
    if settings.get('cognitive_enabled', '1') != '1' or settings.get('memory_updates_enabled', '1') != '1':
        return []
    signals = extract_signals(content)
    if not signals:
        return []
    candidates = []
    with connect() as db:
        excluded = [row[0] for row in db.execute('SELECT topic FROM cognitive_exclusions WHERE user_id=?', (LOCAL_USER_ID,))]
        rejected = [dict(row) for row in db.execute('SELECT statement,dimension FROM cognitive_rejections WHERE user_id=?', (LOCAL_USER_ID,))]
        existing = [dict(row) for row in db.execute(
            "SELECT * FROM cognitive_observations WHERE user_id=? AND persona_id=? AND status IN ('confirmed','partially_confirmed','pending','uncertain')",
            (LOCAL_USER_ID, persona_id),
        )]
        for signal in signals:
            if any(topic in signal['statement'] for topic in excluded) or any(
                (not item['dimension'] or item['dimension'] == signal['dimension']) and similar(signal['statement'], item['statement'], 0.42)
                for item in rejected
            ):
                continue
            match = next((row for row in existing if row['dimension'] == signal['dimension'] and similar(row['statement'], signal['statement'])), None)
            if match:
                duplicate = db.execute(
                    'SELECT 1 FROM cognitive_evidence WHERE observation_id=? AND conversation_id IS ? AND evidence=?',
                    (match['id'], conversation_id, signal['evidence']),
                ).fetchone()
                if duplicate:
                    continue
                observation_id = match['id']
            else:
                observation_id = str(uuid.uuid4())
                status = 'pending' if settings.get('require_confirmation', '1') == '1' else 'uncertain'
                db.execute(
                    'INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,evidence_count,distinct_contexts,supporting_json,confidence_level,source_conversation_id,persona_id,user_id,evidence_class,context_note,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (observation_id, signal['dimension'], signal['statement'], status, 'ai_inference', 1, 1,
                     json.dumps([signal['evidence']], ensure_ascii=False), '极低', conversation_id, persona_id,
                     LOCAL_USER_ID, 'situational', signal['context_note'], signal['fingerprint']),
                )
            message = db.execute(
                "SELECT id FROM messages WHERE conversation_id=? AND role='user' AND content=? ORDER BY id DESC LIMIT 1",
                (conversation_id, content),
            ).fetchone() if conversation_id else None
            db.execute(
                'INSERT INTO cognitive_evidence(id,observation_id,conversation_id,message_id,evidence,evidence_type,source_type,context_note) VALUES(?,?,?,?,?,?,?,?)',
                (str(uuid.uuid4()), observation_id, conversation_id, message['id'] if message else None,
                 signal['evidence'], 'support', 'user_report', signal['context_note']),
            )
            evidence = db.execute(
                "SELECT evidence,created_at,conversation_id FROM cognitive_evidence WHERE observation_id=? AND evidence_type='support' ORDER BY created_at",
                (observation_id,),
            ).fetchall()
            count = len(evidence)
            contexts = len({row['conversation_id'] for row in evidence if row['conversation_id']}) or 1
            span = _days_between(evidence[0]['created_at'], evidence[-1]['created_at']) if evidence else 0
            repeated = count >= 3 and contexts >= 2 and span >= 7
            has_counter = bool(json.loads(match['counter_evidence_json'] or '[]')) if match else False
            classification = 'explicit_fact' if match and match['evidence_class'] == 'explicit_fact' else 'repeated' if repeated else 'situational'
            confidence = '用户确认' if classification == 'explicit_fact' else confidence_label(count, has_counter, contexts) if repeated else '极低'
            supporting = [row['evidence'] for row in evidence[-12:]]
            db.execute(
                'UPDATE cognitive_observations SET evidence_count=?,distinct_contexts=?,supporting_json=?,confidence_level=?,evidence_class=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND persona_id=?',
                (count, contexts, json.dumps(supporting, ensure_ascii=False), confidence, classification,
                 observation_id, LOCAL_USER_ID, persona_id),
            )
            candidates.append({'id': observation_id, 'dimension': signal['dimension'], 'statement': signal['statement'],
                               'evidence_class': classification, 'confidence_label': confidence, 'evidence_count': count})
    return candidates
