from ..cognitive_engine.confidence_engine import confidence_label

def format_observation(row: dict) -> dict:
    item=dict(row)
    item['confidence_label']=confidence_label(int(item.get('evidence_count') or 0), bool(item.get('counter_evidence_json') not in (None,'[]','')) or item.get('status')=='disputed', int(item.get('distinct_contexts') or 1))
    return item
