import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ShieldCheck, Trash2, X } from 'lucide-react'

type Memory = { id:number; category:string; content:string; kind:string; confidence:number }
type Props = { onClose:()=>void }

export default function MemoryEditor({onClose}:Props) {
  const [items,setItems]=useState<Memory[]>([])
  const [enabled,setEnabled]=useState(false)
  const [editing,setEditing]=useState(0)
  const [category,setCategory]=useState('个人观察')
  const [content,setContent]=useState('')
  const [kind,setKind]=useState('self_report')
  const [confidence,setConfidence]=useState(0.7)
  const [error,setError]=useState('')
  const refresh=async()=>{try{const r=await fetch('/api/memories');if(!r.ok)throw new Error();const data=await r.json();setItems(data.items);setEnabled(data.enabled)}catch{setError('无法读取本地记忆。请确认后端服务已启动。')}}
  useEffect(()=>{void refresh()},[])
  const reset=()=>{setEditing(0);setCategory('个人观察');setContent('');setKind('self_report');setConfidence(0.7)}
  const save=async(e:FormEvent)=>{e.preventDefault();setError('');try{const response=await fetch(editing?`/api/memories/${editing}`:'/api/memories',{method:editing?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category,content,kind,confidence})});if(!response.ok)throw new Error();reset();await refresh()}catch{setError('保存失败，请稍后重试。')}}
  const toggle=async()=>{try{const r=await fetch('/api/memories/enabled',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!enabled})});if(!r.ok)throw new Error();setEnabled(!enabled)}catch{setError('更新记忆设置失败。')}}
  return <div className="memory-editor-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="memory-modal" role="dialog" aria-modal="true" aria-labelledby="memory-title"><header><div><span className="panel-kicker">仅保存在此设备</span><h2 id="memory-title">记忆与隐私</h2></div><button className="icon-btn" onClick={onClose} aria-label="关闭"><X size={18}/></button></header><div className="memory-switch-row"><div><strong>允许使用长期记忆</strong><p>仅使用你保存的内容理解上下文；推测会明确标记。</p></div><button role="switch" aria-checked={enabled} className={`switch ${enabled?'on':''}`} onClick={toggle}><i/></button></div><div className="memory-list-title">已保存的记忆 <span>{items.length}</span></div><div className="memory-list">{items.length?items.map(m=><div className="memory-row" key={m.id}><div><span className="memory-category">{m.category} · {m.kind==='fact'?'事实':m.kind==='hypothesis'?'推测':'自述'} · {Math.round(m.confidence*100)}%</span><p>{m.content}</p><button className="memory-edit" onClick={()=>{setEditing(m.id);setCategory(m.category);setContent(m.content);setKind(m.kind);setConfidence(m.confidence)}}>编辑</button></div><button className="icon-btn" title="删除记忆" onClick={async()=>{await fetch(`/api/memories/${m.id}`,{method:'DELETE'});await refresh()}}><Trash2 size={15}/></button></div>):<div className="memory-empty">尚无记忆。只有你明确保存的内容才会用于后续对话。</div>}</div><form className="memory-form" onSubmit={save}><div className="memory-form-title">{editing?'修改记忆':'保存一条记忆'}</div><div className="memory-form-row"><input aria-label="记忆分类" value={category} onChange={e=>setCategory(e.target.value)} maxLength={40} required/><select aria-label="信息类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="fact">事实</option><option value="self_report">我的自述</option><option value="hypothesis">待验证的推测</option></select></div><textarea aria-label="记忆内容" value={content} onChange={e=>setContent(e.target.value)} maxLength={1000} placeholder="只记录你希望未来对话参考的内容" rows={2} required/><label className="confidence-label">置信度 <input type="range" min="0" max="1" step="0.1" value={confidence} onChange={e=>setConfidence(Number(e.target.value))}/><span>{Math.round(confidence*100)}%</span></label><div className="memory-form-actions"><button type="button" onClick={reset}>清空</button><button type="submit" disabled={!content.trim()}>保存</button></div></form>{error&&<div className="memory-error">{error}</div>}<div className="privacy-foot"><ShieldCheck size={15}/> 对话和记忆保存在本地 SQLite，不会发送到云端。</div></section></div>
}
