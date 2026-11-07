"""Read-only integration of persona observations for the user's own profile."""
import json
import uuid

from ..db import connect
from ..persona_context import LOCAL_USER_ID
from .cognitive_profile import DIMENSIONS, DIMENSION_LABELS, PERSONA_NAMES, canonical_dimension, profile_shape

VISIBLE = ('confirmed', 'partially_confirmed', 'pending', 'uncertain')


def _rows(db):
    rows = [dict(row) for row in db.execute(
        'SELECT * FROM cognitive_observations WHERE user_id=? ORDER BY updated_at DESC', (LOCAL_USER_ID,),
    )]
    for row in rows:
        row['canonical_dimension'] = canonical_dimension(row['dimension'])
        row['persona_name'] = PERSONA_NAMES.get(row['persona_id'], '我自己' if row['persona_id'] == 'profile' else '旧记录')
        row['evidence_class'] = row.get('evidence_class') or 'hypothesis'
    return rows


def profile_view() -> dict:
    with connect() as db:
        rows = _rows(db)
        settings = dict(db.execute('SELECT key,value FROM cognitive_settings'))
        exclusions = [dict(row) for row in db.execute('SELECT * FROM cognitive_exclusions WHERE user_id=? ORDER BY created_at DESC', (LOCAL_USER_ID,))]
        changes = [dict(row) for row in db.execute(
            'SELECT * FROM cognitive_evolution WHERE user_id=? ORDER BY occurred_at DESC LIMIT 20', (LOCAL_USER_ID,),
        )]
        contradictions = [dict(row) for row in db.execute(
            "SELECT * FROM cognitive_contradictions WHERE user_id=? AND status='pending' ORDER BY created_at DESC", (LOCAL_USER_ID,),
        )]
    visible = [row for row in rows if row['status'] in VISIBLE]
    dimensions = profile_shape(visible)
    confirmed = [row for row in visible if row['status'] in ('confirmed', 'partially_confirmed')]
    return {
        'dimensions': dimensions, 'dimension_labels': DIMENSION_LABELS,
        'dimensions_order': DIMENSIONS, 'all_observations': visible,
        'rejected_count': sum(row['status'] == 'disputed' for row in rows),
        'summary': {
            'confirmed_count': len(confirmed),
            'pending_count': sum(row['status'] in ('pending', 'uncertain') for row in visible),
            'covered_dimensions': [dimension for dimension in DIMENSIONS if any(row['canonical_dimension'] == dimension for row in confirmed)],
            'last_updated': max((row['updated_at'] for row in rows), default=None),
            'recent_changes': changes[:3],
            'coverage_note': '覆盖维度只反映资料分布，不代表 AI 理解的准确率。',
        },
        'changes': changes, 'contradictions': contradictions,
        'exclusions': exclusions, 'settings': settings,
    }


def create_unified_snapshot(reason: str = 'manual') -> dict:
    view = profile_view()
    snapshot_id = str(uuid.uuid4())
    payload = {
        'dimensions': {key: [dict(row) for row in values if row['status'] in ('confirmed', 'partially_confirmed')]
                       for key, values in view['dimensions'].items()},
        'summary': view['summary'],
    }
    with connect() as db:
        db.execute('INSERT INTO cognitive_snapshots(id,reason,profile_json,persona_id,user_id) VALUES(?,?,?,?,?)',
                   (snapshot_id, reason, json.dumps(payload, ensure_ascii=False), 'profile', LOCAL_USER_ID))
        return dict(db.execute('SELECT * FROM cognitive_snapshots WHERE id=? AND user_id=?', (snapshot_id, LOCAL_USER_ID)).fetchone())


def compare_snapshots(first_id: str, second_id: str) -> dict:
    with connect() as db:
        rows = db.execute('SELECT id,created_at,profile_json FROM cognitive_snapshots WHERE id IN (?,?) AND user_id=? AND persona_id=?',
                          (first_id, second_id, LOCAL_USER_ID, 'profile')).fetchall()
    if len(rows) != 2:
        raise LookupError('画像快照不存在')
    values = {row['id']: row for row in rows}
    first = json.loads(values[first_id]['profile_json'])['dimensions']
    second = json.loads(values[second_id]['profile_json'])['dimensions']
    changes = []
    for dimension in DIMENSIONS:
        before = {row['id']: row['statement'] for row in first.get(dimension, [])}
        after = {row['id']: row['statement'] for row in second.get(dimension, [])}
        if before != after:
            changes.append({'dimension': dimension, 'label': DIMENSION_LABELS[dimension],
                            'added': [value for key, value in after.items() if key not in before],
                            'removed': [value for key, value in before.items() if key not in after],
                            'revised': [{'before': before[key], 'after': after[key]} for key in before.keys() & after.keys() if before[key] != after[key]]})
    return {'first_at': values[first_id]['created_at'], 'second_at': values[second_id]['created_at'],
            'changes': changes, 'note': '记录差异不自动代表进步或退步。'}
