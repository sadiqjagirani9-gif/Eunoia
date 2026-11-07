"""Evidence-grounded local report; never invents missing profile details."""
import json

from ..db import connect
from ..persona_context import LOCAL_USER_ID
from .cognitive_profile import DIMENSIONS, DIMENSION_LABELS
from .unified import profile_view


def _parse_list(raw: str | None) -> list:
    try:
        value = json.loads(raw or '[]')
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def generate_report() -> dict:
    view = profile_view()
    sections = []
    with connect() as db:
        for dimension in DIMENSIONS:
            observations = []
            for row in view['dimensions'][dimension]:
                if row['status'] not in ('confirmed', 'partially_confirmed'):
                    continue
                evidence = [dict(item) for item in db.execute(
                    'SELECT evidence,conversation_id,message_id,created_at,context_note FROM cognitive_evidence WHERE observation_id=? AND evidence_type=? ORDER BY created_at DESC LIMIT 5',
                    (row['id'], 'support'),
                )]
                alternatives = row.get('alternative_explanation', '').strip()
                item = {
                    'id': row['id'], 'statement': row['statement'], 'persona': row['persona_name'],
                    'evidence_class': row['evidence_class'], 'confidence': row['confidence_level'],
                    'source_type': row['source_type'], 'claim_kind': row.get('claim_kind', 'observation'),
                    'context': row.get('context_note', ''),
                    'evidence': evidence, 'counter_evidence': _parse_list(row.get('counter_evidence_json')),
                    'alternative_explanation': alternatives or '尚无足够资料区分情境影响与长期倾向。',
                    'limitation': '该观察只适用于已记录的情境；用户可随时修正。',
                }
                if dimension == 'blindspots' and (row['evidence_class'] != 'repeated' or not evidence or not alternatives):
                    continue
                observations.append(item)
            sections.append({
                'dimension': dimension, 'title': DIMENSION_LABELS[dimension],
                'observations': observations,
                'status': '有已确认线索' if observations else '信息不足，暂时无法形成判断',
                'open_questions': [row['statement'] for row in view['dimensions'][dimension] if row['status'] in ('pending', 'uncertain')][:3],
            })
    anchors = [item for section in sections for item in section['observations']]
    questions = []
    for item in anchors[:5]:
        if item['counter_evidence']:
            questions.append(f"你曾说“{item['statement']}”，也补充了“{item['counter_evidence'][0]}”。两者分别发生在什么情境？")
        elif item['context']:
            questions.append(f"关于“{item['statement']}”，你提到的情境是“{item['context']}”。换一个情境，你的判断会怎样变化？")
        elif item['evidence_class'] == 'repeated':
            questions.append(f"“{item['statement']}”在几次记录中出现。有没有一次相反的经历，能帮助你看清它的边界？")
        else:
            questions.append(f"你确认过“{item['statement']}”。它对你最近一次具体选择产生了什么影响？")
    return {
        'title': '个人认知画像报告', 'sections': sections,
        'conflicts': view['contradictions'],
        'recent_changes': view['changes'][:10],
        'questions': questions,
        'question_note': '现有证据不足以生成五个有个人依据的问题。' if len(questions) < 5 else '',
        'method_note': '报告只整理已确认且可追溯的资料；待确认内容单独列出。没有足够证据的维度保持空白。人格间不同观察保留各自来源。',
    }
