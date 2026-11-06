from ..db import connect

def updates_enabled() -> bool:
    with connect() as db:
        rows=dict(db.execute("SELECT key,value FROM settings WHERE key IN ('cognitive_enabled','memory_updates_enabled')").fetchall())
    return rows.get('cognitive_enabled','1')=='1' and rows.get('memory_updates_enabled','1')=='1'
