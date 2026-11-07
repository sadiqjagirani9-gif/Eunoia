import json
import uuid
from ..db import connect

def create_snapshot(reason: str='manual', persona_id: str='anatomy', user_id: str='local') -> dict:
    with connect() as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM cognitive_observations WHERE user_id=? AND persona_id=? AND status IN ('confirmed','partially_confirmed') ORDER BY dimension,created_at",(user_id,persona_id)).fetchall()]
        snapshot_id=str(uuid.uuid4())
        db.execute("INSERT INTO cognitive_snapshots(id,reason,profile_json,persona_id,user_id) VALUES(?,?,?,?,?)", (snapshot_id, reason, json.dumps(rows,ensure_ascii=False),persona_id,user_id))
        return dict(db.execute('SELECT * FROM cognitive_snapshots WHERE id=?',(snapshot_id,)).fetchone())
