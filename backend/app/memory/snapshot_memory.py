import json
import uuid
from ..db import connect

def create_snapshot(reason: str='manual') -> dict:
    with connect() as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM cognitive_observations WHERE status IN ('confirmed','partially_confirmed') ORDER BY dimension,created_at").fetchall()]
        snapshot_id=str(uuid.uuid4())
        db.execute("INSERT INTO cognitive_snapshots(id,reason,profile_json) VALUES(?,?,?)", (snapshot_id, reason, json.dumps(rows,ensure_ascii=False)))
        return dict(db.execute('SELECT * FROM cognitive_snapshots WHERE id=?',(snapshot_id,)).fetchone())
