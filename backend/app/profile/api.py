import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import connect
from ..memory.short_term_memory import expiry
from ..memory.snapshot_memory import create_snapshot
from ..profile.cognitive_profile import DIMENSIONS, profile_shape
from ..profile.profile_updater import extract_signals
from ..cognitive_engine.confidence_engine import confidence_label
from ..cognitive_engine.contradiction_detector import compare
from ..cognitive_engine.cognitive_evolution import report

router=APIRouter(prefix='/api/cognitive',tags=['cognitive-profile'])

class ObserveInput(BaseModel):
    content:str=Field(min_length=1,max_length=12000)
    conversation_id:str|None=None

class FeedbackInput(BaseModel):
    rating:str
    explanation:str=''

class ResolveInput(BaseModel):
    status:str
    explanation:str=''

class ObservationEdit(BaseModel):
    statement:str=Field(min_length=1,max_length=1000)
    user_explanation:str=''

class SettingsInput(BaseModel):
    cognitive_enabled:bool|None=None
    memory_updates_enabled:bool|None=None
    require_confirmation:bool|None=None
    short_term_days:int|None=Field(default=None,ge=1,le=365)

@router.get('/profile')
def get_profile():
    with connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM cognitive_observations ORDER BY updated_at DESC').fetchall()]
        settings=dict(db.execute('SELECT key,value FROM cognitive_settings').fetchall())
        contradictions=[dict(r) for r in db.execute("SELECT * FROM cognitive_contradictions WHERE status='pending' ORDER BY created_at DESC").fetchall()]
    for row in rows: row['confidence_label']=confidence_label(row['evidence_count'], bool(json.loads(row['counter_evidence_json'] or '[]')) or row['status']=='disputed', row['distinct_contexts'])
    return {'dimensions':profile_shape(rows),'all_observations':rows,'contradictions':contradictions,'settings':settings,'dimensions_order':DIMENSIONS}

@router.post('/observe')
def observe(body:ObserveInput):
    with connect() as db:
        settings=dict(db.execute('SELECT key,value FROM cognitive_settings').fetchall())
        if settings.get('cognitive_enabled','1')!='1' or settings.get('memory_updates_enabled','1')!='1':
            return {'paused':True,'candidates':[],'contradictions':[]}
        existing=[dict(r) for r in db.execute("SELECT * FROM cognitive_observations WHERE status IN ('confirmed','partially_confirmed','pending')").fetchall()]
    signals=extract_signals(body.content)
    candidates=[]
    for item in signals:
        match=next((r for r in existing if r['dimension']==item['dimension'] and r['statement']==item['statement']),None)
        if match:
            with connect() as db:
                db.execute('INSERT INTO cognitive_evidence(id,observation_id,conversation_id,evidence,evidence_type,source_type) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),match['id'],body.conversation_id,item['evidence'],'support','user_report'))
                count=db.execute('SELECT COUNT(*) FROM cognitive_evidence WHERE observation_id=?',(match['id'],)).fetchone()[0]
                contexts=db.execute('SELECT COUNT(DISTINCT conversation_id) FROM cognitive_evidence WHERE observation_id=? AND conversation_id IS NOT NULL',(match['id'],)).fetchone()[0]
                db.execute('UPDATE cognitive_observations SET evidence_count=?,distinct_contexts=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(count,max(1,contexts),match['id']))
                contexts=db.execute('SELECT distinct_contexts FROM cognitive_observations WHERE id=?',(match['id'],)).fetchone()[0]
                db.execute('UPDATE cognitive_observations SET confidence_level=? WHERE id=?',(confidence_label(count,False,contexts),match['id']))
            candidates.append({'id':match['id'],'dimension':item['dimension'],'statement':item['statement'],'status':match['status'],'evidence_count':count,'confidence_label':confidence_label(count,False,contexts)})
            continue
        observation_id=str(uuid.uuid4())
        status='pending' if settings.get('require_confirmation','1')=='1' else 'uncertain'
        with connect() as db:
            db.execute('INSERT INTO cognitive_observations(id,dimension,statement,status,source_type,evidence_count,distinct_contexts,supporting_json,confidence_level,source_conversation_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(observation_id,item['dimension'],item['statement'],status,'ai_inference',1,1,json.dumps([item['evidence']],ensure_ascii=False),'极低',body.conversation_id))
            db.execute('INSERT INTO cognitive_evidence(id,observation_id,conversation_id,evidence,evidence_type,source_type) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),observation_id,body.conversation_id,item['evidence'],'support','user_report'))
        candidates.append({'id':observation_id,**item,'status':status,'confidence_label':'极低'})
    with connect() as db:
        db.execute('DELETE FROM short_term_memories WHERE expires_at<CURRENT_TIMESTAMP')
        if body.conversation_id:
            db.execute('INSERT INTO short_term_memories(id,conversation_id,content_json,expires_at) VALUES(?,?,?,?)',(str(uuid.uuid4()),body.conversation_id,json.dumps({'signals':[x['statement'] for x in signals]},ensure_ascii=False),expiry(int(settings.get('short_term_days','30')))))
        active=[dict(r) for r in db.execute("SELECT * FROM cognitive_observations WHERE status IN ('confirmed','partially_confirmed')").fetchall()]
    contradictions=compare(active,body.content)
    for item in contradictions:
        with connect() as db:
            prior=db.execute("SELECT id FROM cognitive_contradictions WHERE status='pending' AND past_statement=? AND current_statement=?",(item['past'],item['present'])).fetchone()
            if prior:item['id']=prior['id']
            else:
                item['id']=str(uuid.uuid4())
                db.execute('INSERT INTO cognitive_contradictions(id,observation_id,past_statement,current_statement,question) VALUES(?,?,?,?,?)',(item['id'],item.get('observation_id'),item['past'],item['present'],item['question']))
    with connect() as db:
        previous=db.execute("SELECT created_at FROM cognitive_snapshots ORDER BY created_at DESC LIMIT 1").fetchone()
    if not previous or db_date(previous['created_at']) < db_date(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))-30*86400:
        create_snapshot('monthly')
    return {'paused':False,'candidates':candidates,'contradictions':contradictions}

def db_date(value:str)->int:
    from datetime import datetime
    return int(datetime.strptime(value[:19],'%Y-%m-%d %H:%M:%S').timestamp())

@router.get('/observations/{observation_id}/evidence')
def evidence(observation_id:str):
    with connect() as db:
        rows=db.execute('SELECT * FROM cognitive_evidence WHERE observation_id=? ORDER BY created_at',(observation_id,)).fetchall()
    return [dict(r) for r in rows]

@router.patch('/observations/{observation_id}')
def edit_observation(observation_id:str,body:ObservationEdit):
    with connect() as db:
        previous=db.execute('SELECT dimension,statement FROM cognitive_observations WHERE id=?',(observation_id,)).fetchone()
        cur=db.execute('UPDATE cognitive_observations SET statement=?,user_explanation=?,status="confirmed",updated_at=CURRENT_TIMESTAMP WHERE id=?',(body.statement,body.user_explanation,observation_id))
        if previous and previous['statement']!=body.statement:
            db.execute('INSERT INTO cognitive_evolution(id,dimension,summary,past_behavior,recent_behavior,evidence_json,possible_causes,uncertainties) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),previous['dimension'],'用户修正了认知观察',previous['statement'],body.statement,json.dumps([body.user_explanation],ensure_ascii=False),'用户的自我校准','变化是否长期稳定仍需后续观察。'))
    if not cur.rowcount:raise HTTPException(404,'认知观察不存在')
    return {'updated':True}

@router.delete('/observations/{observation_id}')
def delete_observation(observation_id:str):
    with connect() as db:cur=db.execute('DELETE FROM cognitive_observations WHERE id=?',(observation_id,))
    if not cur.rowcount:raise HTTPException(404,'认知观察不存在')
    return {'deleted':True}

@router.post('/observations/{observation_id}/feedback')
def feedback(observation_id:str,body:FeedbackInput):
    mapping={'agree':'confirmed','partial':'partially_confirmed','disagree':'disputed','unsure':'uncertain'}
    if body.rating not in mapping:raise HTTPException(422,'rating 必须为 agree、partial、disagree 或 unsure')
    with connect() as db:
        if not db.execute('SELECT 1 FROM cognitive_observations WHERE id=?',(observation_id,)).fetchone():raise HTTPException(404,'认知观察不存在')
        db.execute('INSERT INTO cognitive_feedback(id,observation_id,rating,explanation) VALUES(?,?,?,?)',(str(uuid.uuid4()),observation_id,body.rating,body.explanation))
        observed=db.execute('SELECT dimension,statement,counter_evidence_json FROM cognitive_observations WHERE id=?',(observation_id,)).fetchone()
        if body.rating=='disagree' and body.explanation:
            counter=json.loads(observed['counter_evidence_json'] or '[]');counter.append(body.explanation)
            db.execute('UPDATE cognitive_observations SET counter_evidence_json=? WHERE id=?',(json.dumps(counter,ensure_ascii=False),observation_id))
            db.execute('INSERT INTO cognitive_evidence(id,observation_id,evidence,evidence_type,source_type) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),observation_id,body.explanation,'counter','user_report'))
        db.execute('UPDATE cognitive_observations SET status=?,user_explanation=?,confidence_level=CASE WHEN ? IN ("disagree","unsure") THEN "极低" ELSE confidence_level END,updated_at=CURRENT_TIMESTAMP WHERE id=?',(mapping[body.rating],body.explanation,body.rating,observation_id))
        db.execute('INSERT INTO cognitive_evolution(id,dimension,summary,past_behavior,recent_behavior,evidence_json,possible_causes,uncertainties) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),observed['dimension'],'用户校准了一条认知观察',observed['statement'],body.rating,json.dumps([body.explanation],ensure_ascii=False),'用户反馈','该反馈仅说明用户对本条观察的当前评价。'))
    return {'status':mapping[body.rating]}

@router.post('/contradictions/{contradiction_id}/resolve')
def resolve(contradiction_id:str,body:ResolveInput):
    if body.status not in {'confirmed','partially_confirmed','rejected','uncertain'}:raise HTTPException(422,'无效的确认状态')
    with connect() as db:
        cur=db.execute('UPDATE cognitive_contradictions SET status=?,user_response=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?',(body.status,body.explanation,contradiction_id))
        row=db.execute('SELECT observation_id FROM cognitive_contradictions WHERE id=?',(contradiction_id,)).fetchone()
        if row and row['observation_id'] and body.status in {'rejected','uncertain'}:
            db.execute('UPDATE cognitive_observations SET status=?,user_explanation=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('disputed' if body.status=='rejected' else 'uncertain',body.explanation,row['observation_id']))
    if not cur.rowcount:raise HTTPException(404,'认知差异不存在')
    return {'resolved':True}

@router.get('/evolution')
def evolution(period:str='month'):
    return report(period if period in {'month','quarter'} else 'month')

@router.post('/snapshot')
def snapshot():return create_snapshot()

@router.get('/snapshots')
def snapshots():
    with connect() as db:return [dict(r) for r in db.execute('SELECT * FROM cognitive_snapshots ORDER BY created_at DESC').fetchall()]

@router.get('/settings')
def get_settings():
    with connect() as db:return dict(db.execute('SELECT key,value FROM cognitive_settings').fetchall())

@router.put('/settings')
def set_settings(body:SettingsInput):
    for key,value in body.model_dump(exclude_none=True).items():
        with connect() as db:db.execute('INSERT INTO cognitive_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(int(value)) if isinstance(value,bool) else str(value)))
    return get_settings()

@router.get('/export')
def export_data():
    with connect() as db:
        data={table:[dict(r) for r in db.execute(f'SELECT * FROM {table}').fetchall()] for table in ('conversations','messages','cognitive_observations','cognitive_evidence','cognitive_snapshots','cognitive_evolution','cognitive_contradictions','cognitive_feedback','short_term_memories','memories','people','relationships','relationship_events','important_events','emotional_states','counterfactual_cases','simulation_branches','analysis_reports')}
        data['settings']=[dict(r) for r in db.execute('SELECT * FROM cognitive_settings').fetchall()]
        data['app_settings']=[dict(r) for r in db.execute('SELECT * FROM settings').fetchall()]
    return {'format':'eunoia-cognitive-v3','exported_at':datetime.now(timezone.utc).isoformat(),'data':data}

@router.delete('/profile')
def clear_profile():
    create_snapshot('before_clear')
    with connect() as db:
        db.execute('DELETE FROM cognitive_observations');db.execute('DELETE FROM cognitive_snapshots');db.execute('DELETE FROM cognitive_evolution');db.execute('DELETE FROM cognitive_contradictions');db.execute('DELETE FROM short_term_memories')
    return {'cleared':True}

@router.post('/restore')
def restore_data(payload:dict):
    if payload.get('format')!='eunoia-cognitive-v3' or not isinstance(payload.get('data'),dict):raise HTTPException(422,'备份格式不受支持')
    data=payload['data']
    # Restore records additively so importing a backup never overwrites newer local data.
    with connect() as db:
        for item in data.get('app_settings',[]):
            if {'key','value'}.issubset(item):db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(item['key'],item['value']))
        for item in data.get('settings',[]):
            if {'key','value'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_settings(key,value) VALUES(?,?)',(item['key'],item['value']))
        for item in data.get('conversations',[]):
            if {'id','title','mode'}.issubset(item):db.execute('INSERT OR IGNORE INTO conversations(id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)',(item['id'],item['title'],item['mode'],item.get('created_at'),item.get('updated_at')))
        for item in data.get('messages',[]):
            if {'id','conversation_id','role','content'}.issubset(item):db.execute('INSERT OR IGNORE INTO messages(id,conversation_id,role,content,analysis_json,created_at) VALUES(?,?,?,?,?,?)',(item['id'],item['conversation_id'],item['role'],item['content'],item.get('analysis_json'),item.get('created_at')))
        for item in data.get('cognitive_observations',[]):
            required={'id','dimension','statement','status','source_type'}
            if not required.issubset(item) or item['dimension'] not in DIMENSIONS:continue
            db.execute('INSERT OR REPLACE INTO cognitive_observations(id,dimension,statement,status,source_type,evidence_count,distinct_contexts,supporting_json,counter_evidence_json,confidence_level,source_conversation_id,user_explanation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(item['id'],item['dimension'],item['statement'],item['status'],item['source_type'],int(item.get('evidence_count',1)),int(item.get('distinct_contexts',1)),item.get('supporting_json','[]'),item.get('counter_evidence_json','[]'),item.get('confidence_level','极低'),item.get('source_conversation_id'),item.get('user_explanation','')))
        for item in data.get('cognitive_evidence',[]):
            if {'id','observation_id','evidence'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_evidence(id,observation_id,evidence,evidence_type,source_type) VALUES(?,?,?,?,?)',(item['id'],item['observation_id'],item['evidence'],item.get('evidence_type','support'),item.get('source_type','user_report')))
        for item in data.get('cognitive_snapshots',[]):
            if {'id','profile_json'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_snapshots(id,reason,profile_json,created_at) VALUES(?,?,?,?)',(item['id'],item.get('reason','restored'),item['profile_json'],item.get('created_at')))
        for item in data.get('cognitive_evolution',[]):
            if {'id','dimension','summary'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_evolution(id,dimension,summary,past_behavior,recent_behavior,evidence_json,possible_causes,uncertainties,created_at,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(item['id'],item['dimension'],item['summary'],item.get('past_behavior',''),item.get('recent_behavior',''),item.get('evidence_json','[]'),item.get('possible_causes',''),item.get('uncertainties',''),item.get('created_at'),item.get('occurred_at')))
        for item in data.get('cognitive_contradictions',[]):
            if {'id','past_statement','current_statement','question'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_contradictions(id,observation_id,past_statement,current_statement,question,status,user_response,created_at,resolved_at) VALUES(?,?,?,?,?,?,?,?,?)',(item['id'],item.get('observation_id'),item['past_statement'],item['current_statement'],item['question'],item.get('status','pending'),item.get('user_response',''),item.get('created_at'),item.get('resolved_at')))
        for item in data.get('cognitive_feedback',[]):
            if {'id','observation_id','rating'}.issubset(item):db.execute('INSERT OR IGNORE INTO cognitive_feedback(id,observation_id,rating,explanation,created_at) VALUES(?,?,?,?,?)',(item['id'],item['observation_id'],item['rating'],item.get('explanation',''),item.get('created_at')))
        for item in data.get('short_term_memories',[]):
            if {'id','conversation_id','content_json','expires_at'}.issubset(item):db.execute('INSERT OR IGNORE INTO short_term_memories(id,conversation_id,content_json,expires_at,created_at) VALUES(?,?,?,?,?)',(item['id'],item['conversation_id'],item['content_json'],item['expires_at'],item.get('created_at')))
        for item in data.get('analysis_reports',[]):
            if {'id','report_type','content_json'}.issubset(item):db.execute('INSERT OR IGNORE INTO analysis_reports(id,conversation_id,report_type,content_json,created_at) VALUES(?,?,?,?,?)',(item['id'],item.get('conversation_id'),item['report_type'],item['content_json'],item.get('created_at')))
        for item in data.get('memories',[]):
            if {'category','content','kind'}.issubset(item) and item['kind'] in {'fact','self_report','hypothesis'}:
                db.execute('INSERT INTO memories(category,content,kind,confidence) VALUES(?,?,?,?)',(item['category'],item['content'],item['kind'],max(0,min(1,float(item.get('confidence',.5))))))
        for item in data.get('people',[]):
            if {'id','name'}.issubset(item):db.execute('INSERT OR IGNORE INTO people(id,name,category,notes,hidden,last_mentioned_at) VALUES(?,?,?,?,?,?)',(item['id'],item['name'],item.get('category','other'),item.get('notes',''),int(item.get('hidden',0)),item.get('last_mentioned_at')))
        for item in data.get('important_events',[]):
            if {'id','title'}.issubset(item):db.execute('INSERT OR IGNORE INTO important_events(id,title,description,occurred_at,source_type,confidence,conversation_id) VALUES(?,?,?,?,?,?,?)',(item['id'],item['title'],item.get('description',''),item.get('occurred_at'),item.get('source_type','user_report'),item.get('confidence',.5),item.get('conversation_id')))
        for item in data.get('relationships',[]):
            if {'id','source_id','target_id','kind','direction'}.issubset(item):db.execute('INSERT OR IGNORE INTO relationships(id,source_id,target_id,kind,direction,strength,source_type,confidence) VALUES(?,?,?,?,?,?,?,?)',(item['id'],item['source_id'],item['target_id'],item['kind'],item['direction'],item.get('strength',.5),item.get('source_type','user_report'),item.get('confidence',.5)))
        for item in data.get('relationship_events',[]):
            if {'id','summary'}.issubset(item):db.execute('INSERT OR IGNORE INTO relationship_events(id,relationship_id,person_id,event_id,summary,occurred_at,strength_before,strength_after,source_type,confidence,conversation_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(item['id'],item.get('relationship_id'),item.get('person_id'),item.get('event_id'),item['summary'],item.get('occurred_at'),item.get('strength_before'),item.get('strength_after'),item.get('source_type','user_report'),item.get('confidence',.5),item.get('conversation_id')))
        for item in data.get('emotional_states',[]):
            if {'id','emotions_json'}.issubset(item):db.execute('INSERT OR IGNORE INTO emotional_states(id,person_id,event_id,emotions_json,intensity,source_type,confidence,occurred_at,conversation_id) VALUES(?,?,?,?,?,?,?,?,?)',(item['id'],item.get('person_id'),item.get('event_id'),item['emotions_json'],item.get('intensity',.5),item.get('source_type','user_report'),item.get('confidence',.5),item.get('occurred_at'),item.get('conversation_id')))
        for item in data.get('counterfactual_cases',[]):
            if {'id','title','background'}.issubset(item):db.execute('INSERT OR IGNORE INTO counterfactual_cases(id,title,background,assumptions_json,result_json,conversation_id,created_at) VALUES(?,?,?,?,?,?,?)',(item['id'],item['title'],item['background'],item.get('assumptions_json','[]'),item.get('result_json','{}'),item.get('conversation_id'),item.get('created_at')))
        for item in data.get('simulation_branches',[]):
            if {'id','case_id','path_key','choice'}.issubset(item):db.execute('INSERT OR IGNORE INTO simulation_branches(id,case_id,parent_id,path_key,choice,short_term,mid_term,long_term,gains_json,costs_json,uncertainties_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(item['id'],item['case_id'],item.get('parent_id'),item['path_key'],item['choice'],item.get('short_term',''),item.get('mid_term',''),item.get('long_term',''),item.get('gains_json','[]'),item.get('costs_json','[]'),item.get('uncertainties_json','[]')))
    return {'restored':True}
