import json
import os
import uuid
from typing import Any
import httpx

from .db import connect
from . import model_config, llm


EMPATHETIC = """你是温柔导师。只关注用户的情绪体验、深层需求、害怕什么、未表达的感受和内在矛盾。先理解再分析，不诊断，不把推测当事实。"""
RATIONAL = """你是理性观察者。只关注可验证事实、行为、证据、现实限制、认知偏差和可行方案。明确区分事实、用户解释和未知；不为了安慰而改变判断，不臆测他人动机。"""

async def _ask(system: str, prompt: str, model: str | None = None, persona: str = 'anatomy') -> str:
    config = model_config.resolve(persona)
    if not config:
        raise ValueError(f"{persona} 尚未配置模型")
    return await llm.complete_chat(config, [{'role':'system','content':system}, {'role':'user','content':prompt}])

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

def graph_snapshot() -> dict:
    with connect() as db:
        people = [dict(row) for row in db.execute("SELECT * FROM people WHERE hidden=0 ORDER BY updated_at DESC").fetchall()]
        relationships = [dict(row) for row in db.execute("SELECT * FROM relationships ORDER BY updated_at DESC").fetchall()]
        events = [dict(row) for row in db.execute("SELECT * FROM relationship_events ORDER BY occurred_at DESC").fetchall()]
    return {'people': people, 'relationships': relationships, 'events': events}

def save_graph(payload: dict) -> dict:
    with connect() as db:
        for item in payload.get('people', []):
            person_id = item.get('id') or str(uuid.uuid4())
            db.execute("INSERT INTO people(id,name,category,notes,hidden,last_mentioned_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,notes=excluded.notes,hidden=excluded.hidden,updated_at=CURRENT_TIMESTAMP", (person_id, item.get('name','未命名人物'), item.get('category','other'), item.get('notes',''), int(bool(item.get('hidden',False)))))
        for item in payload.get('relationships', []):
            source, target = item['source_id'], item['target_id']
            db.execute("INSERT INTO relationships(id,source_id,target_id,kind,direction,strength,source_type,confidence) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,target_id,kind) DO UPDATE SET direction=excluded.direction,strength=excluded.strength,source_type=excluded.source_type,confidence=excluded.confidence,updated_at=CURRENT_TIMESTAMP", (item.get('id') or str(uuid.uuid4()), source, target, item.get('kind','朋友'), item.get('direction','directed'), float(item.get('strength',.5)), item.get('source_type','user_report'), float(item.get('confidence',.7))))
    return graph_snapshot()

async def dual_analysis(text: str, model: str | None = None) -> dict:
    with connect() as db:
        observations=db.execute("SELECT dimension,statement,confidence_level FROM cognitive_observations WHERE status IN ('confirmed','partially_confirmed') ORDER BY updated_at DESC LIMIT 10").fetchall() if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cognitive_observations'").fetchone() else []
    context='\n'.join(f"[{r['dimension']} / {r['confidence_level']}] {r['statement']}" for r in observations)
    if context:text=f"用户已确认的可修正观察（只作上下文）：\n{context}\n\n当前情境：\n{text}"
    facts = await _ask('提取事件事实。只列出用户明确描述的行为、人物和时间，不解释动机。', text, model, 'anatomy')
    mentor = await _ask(EMPATHETIC, f'事件事实：\n{facts}\n\n用户原话：\n{text}\n\n输出温柔导师分析。', model, 'anatomy')
    observer = await _ask(RATIONAL, f'事件事实：\n{facts}\n\n用户原话：\n{text}\n\n输出理性观察者分析。', model, 'debate')
    synthesis = await _ask('你是综合编辑。比较两种分析的分歧，保留情绪事实和逻辑限制，不能把可能性写成定论。', f'事实：{facts}\n温柔导师：{mentor}\n理性观察者：{observer}\n输出观点冲突、综合判断、一个值得思考的问题。', model, 'anatomy')
    with connect() as db:
        db.execute("INSERT INTO analysis_reports(id,report_type,content_json) VALUES(?,?,?)", (str(uuid.uuid4()), 'dual_perspective', _json({'facts':facts,'empathetic':mentor,'rational':observer,'synthesis':synthesis})))
    return {'facts':facts,'empathetic':mentor,'rational':observer,'synthesis':synthesis}

async def simulate(text: str, model: str | None = None) -> dict:
    with connect() as db:
        observations=db.execute("SELECT dimension,statement FROM cognitive_observations WHERE status IN ('confirmed','partially_confirmed') ORDER BY updated_at DESC LIMIT 10").fetchall() if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cognitive_observations'").fetchone() else []
    context='\n'.join(f"[{r['dimension']}] {r['statement']}" for r in observations)
    if context:text=f"长期背景（用户确认的观察，非事实定论）：\n{context}\n\n反事实情境：\n{text}"
    instruction = "建立三条反事实路径：A 原有选择，B 替代选择一，C 替代选择二。每条包含 choice、short_term、mid_term、long_term、gains、costs、uncertainties。禁止精确概率，明确区分事实、推断、假设。只返回 JSON 对象，字段为 branches 数组。"
    raw = await _ask(instruction, text, model, 'guidance')
    try:
        result = json.loads(raw[raw.find('{'):raw.rfind('}')+1])
    except (ValueError, TypeError):
        result = {'branches':[{'choice':'原有选择','short_term':raw,'mid_term':'难以判断','long_term':'难以判断','gains':[],'costs':[],'uncertainties':['模型未返回结构化结果']}]}
    case_id = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO counterfactual_cases(id,title,background,result_json) VALUES(?,?,?,?)", (case_id, text[:80], text, _json(result)))
        for index, branch in enumerate(result.get('branches', [])[:3]):
            db.execute("INSERT INTO simulation_branches(id,case_id,path_key,choice,short_term,mid_term,long_term,gains_json,costs_json,uncertainties_json) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), case_id, chr(65+index), branch.get('choice',f'路径 {index+1}'), branch.get('short_term',''), branch.get('mid_term',''), branch.get('long_term',''), _json(branch.get('gains',[])), _json(branch.get('costs',[])), _json(branch.get('uncertainties',[]))))
    return {'case_id':case_id, 'result':result}
