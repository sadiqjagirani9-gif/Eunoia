import { useState } from 'react'

type Synthesis={sections:{dimension:string;analysis:string;evidence_ids:string[];uncertainties:string}[];questions:{text:string;evidence_ids:string[]}[];note:string}
const personas:Record<string,string>={anatomy:'Evelyn',debate:'Arthur',guidance:'Sophia',self_exploration:'Iris',lucien:'Lucien',felix:'Felix'}

export default function ProfileSynthesis({labels,statements}:{labels:Record<string,string>;statements:Record<string,string>}){
  const [modelPersona,setModelPersona]=useState('self_exploration')
  const [result,setResult]=useState<Synthesis|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const run=async()=>{setBusy(true);setError('');setResult(null);try{
    const response=await fetch('/api/cognitive/report/synthesis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_persona:modelPersona})})
    const data=await response.json()
    if(!response.ok)throw new Error(data.detail||'模型综合失败')
    setResult(data)
  }catch(issue){setError(String(issue))}finally{setBusy(false)}}
  return <section className="profile-report-section"><h3>模型辅助深度综合</h3><p>你主动生成时，已确认的画像观察和原话证据会发送给所选人格绑定的模型服务。云端模型可能产生费用；综合内容不会自动写入画像。</p><div className="profile-compare"><select value={modelPersona} onChange={event=>setModelPersona(event.target.value)}>{Object.entries(personas).map(([id,name])=><option key={id} value={id}>使用 {name} 绑定的模型</option>)}</select><button disabled={busy} onClick={()=>void run()}>{busy?'正在综合…':'生成深度综合'}</button></div>{error&&<p role="alert">{error}</p>}{result&&<><p className="profile-muted">{result.note}</p>{result.sections.map((item,index)=><article key={`${item.dimension}-${index}`}><h4>{labels[item.dimension]||item.dimension}</h4><p>{item.analysis}</p><small>依据：{item.evidence_ids.map(id=>statements[id]||id).join('；')}</small>{item.uncertainties&&<p>仍不确定：{item.uncertainties}</p>}</article>)}{result.questions.length>0&&<article><h4>值得继续探索的问题</h4>{result.questions.map((item,index)=><p key={index}>{index+1}. {item.text}</p>)}</article>}</>}</section>
}
