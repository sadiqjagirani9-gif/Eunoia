from datetime import date
from ..db import connect

def report(period: str='month') -> dict:
    with connect() as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM cognitive_evolution ORDER BY occurred_at DESC LIMIT 100").fetchall()]
    span=90 if period=='quarter' else 31
    cutoff=date.today().fromordinal(date.today().toordinal()-span).isoformat()
    selected=[r for r in rows if str(r['occurred_at'])[:10]>=cutoff]
    return {'period':period,'changes':selected,'past':selected[-1] if selected else None,'recent':selected[0] if selected else None,'note':'变化可能来自成长、环境适应或暂时状态，需要结合情境理解。'}
