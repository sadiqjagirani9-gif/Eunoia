import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { BookOpen, Brain, ChevronDown, CircleHelp, Compass, Heart, Leaf, MessageCircle, Plus, Send, Settings2, ShieldCheck, Sparkles, Star, Trash2, X } from 'lucide-react'
import MemoryEditor from './MemoryEditor'
import CognitiveProfile from './CognitiveProfile'
import KnowledgeManager from './KnowledgeManager'
import './v4.css'

type Mode = 'anatomy'|'debate'|'guidance'|'self_exploration'
type DebateStyle = 'discussion'|'opposition'|'steelman'|'both_sides'
type Conversation = { id: string; title: string; mode: Mode; preview?: string; favorite?: number|boolean }
type Message = { id?: number|string; role: 'user'|'assistant'; content: string; analysis_json?: string|null }
type Memory = { id: number; category: string; content: string; kind: string; confidence: number }

const modes: { id: Mode; label: string; icon: typeof Heart; desc: string; welcome: string }[] = [
  { id:'anatomy', label:'情感解剖', icon:Heart, desc:'温柔剖析情绪，探寻情感深处的真实。', welcome:'我想听见，你沉默背后的声音。' },
  { id:'debate', label:'理性辩论', icon:Sparkles, desc:'以逻辑审视观点，以理性接近真相。', welcome:'质疑一切，唯独不放弃思考。' },
  { id:'guidance', label:'生活指导', icon:Compass, desc:'洞察现实困境，寻找切实可行的出路。', welcome:'人生的答案，要自己走出来。' },
  { id:'self_exploration', label:'自我探索', icon:Brain, desc:'向内探索自我，理解存在与成长。', welcome:'向内凝视，看见真实的自己。' },
]
const personaNames: Record<Mode,string> = { anatomy:'Evelyn', debate:'Arthur', guidance:'Sophia', self_exploration:'Iris' }
const debateStyles: {id: DebateStyle; label: string}[] = [
  {id:'discussion',label:'正常讨论'}, {id:'opposition',label:'反方辩论'},
  {id:'steelman',label:'钢人论证'}, {id:'both_sides',label:'双方辩论'},
]
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type':'application/json', ...(init?.headers || {}) } })
  if (!response.ok) throw new Error((await response.json().catch(()=>({detail:'本地服务暂不可用'}))).detail || '请求失败')
  return response.json()
}

export default function App() {
  const [conversations,setConversations] = useState<Conversation[]>([])
  const [active,setActive] = useState<Conversation|null>(null)
  const [selectedMode,setSelectedMode] = useState<Mode>('guidance')
  const [messages,setMessages] = useState<Message[]>([])
  const [input,setInput] = useState('')
  const [models,setModels] = useState<string[]>([])
  const [model,setModel] = useState('')
  const [online,setOnline] = useState(false)
  const [loading,setLoading] = useState(false)
  const [report,setReport] = useState(false)
  const [debateStyle,setDebateStyle] = useState<DebateStyle>('discussion')
  const [error,setError] = useState('')
  const [memOpen,setMemOpen] = useState(false)
  const [memoryEnabled,setMemoryEnabled] = useState(false)
  const [memories,setMemories] = useState<Memory[]>([])
  const [mobileNav,setMobileNav] = useState(false)
  const [profileOpen,setProfileOpen] = useState(false)
  const [knowledgeOpen,setKnowledgeOpen] = useState(false)
  const currentMode = active?.mode || selectedMode
  const activePersona = personaNames[currentMode] || 'Eunoia'
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const refresh = async () => { try { setConversations(await api<Conversation[]>('/api/conversations')) } catch { /* backend may still be starting */ } }
  const refreshMemories = async () => { try { const m=await api<{enabled:boolean;items:Memory[]}>('/api/memories');setMemoryEnabled(m.enabled);setMemories(m.items) } catch { /* backend may still be starting */ } }
  useEffect(()=>{ refresh(); refreshMemories(); api<{models:string[];default:string}>('/api/models').then(v=>{setModels(v.models);setModel(v.default);setOnline(true)}).catch(()=>setOnline(false)); const timer=setInterval(()=>api<{status:string;ollama:string}>('/api/health').then(v=>setOnline(v.ollama==='connected')).catch(()=>setOnline(false)),8000);return()=>clearInterval(timer)},[])
  useEffect(()=>{bottomRef.current?.scrollIntoView({behavior:'smooth'})},[messages])

  const openConversation = async (c: Conversation) => { setError('');try { const d=await api<{messages:Message[]}>('/api/conversations/'+c.id);setActive(c);setSelectedMode(c.mode);setMessages(d.messages);setMobileNav(false) } catch(e){setError(String(e))} }
  const selectSpace = (mode: Mode) => { setActive(null);setSelectedMode(mode);setMessages([]);setInput('');setError('');setMobileNav(false) }
  const startBlank = () => { setActive(null);setMessages([]);setInput('');setError('');setMobileNav(false) }
  const send = async (text=input) => {
    const content=text.trim();if(!content||loading)return
    let target=active
    if(!target){try{target=await api<Conversation>('/api/conversations',{method:'POST',body:JSON.stringify({mode:selectedMode})});setActive(target);refresh()}catch(e){setError(String(e));return}}
    setInput('');setError('');setLoading(true);setReport(false)
    setMessages(prev=>[...prev,{role:'user',content},{role:'assistant',content:''}])
    try {
      const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:target.id,content,mode:target.mode,deep_report:report,model:model||undefined,debate_style:target.mode==='debate'?debateStyle:undefined})})
      if(!response.ok||!response.body)throw new Error('无法连接本地服务，请确认后端已启动。')
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer=''
      while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const events=buffer.split('\n\n');buffer=events.pop()||'';for(const event of events){const data=event.split('\n').find(line=>line.startsWith('data: '))?.slice(6);if(!data)continue;const payload=JSON.parse(data);if(event.includes('event: error'))throw new Error(payload.message);if(payload.token)setMessages(prev=>{const next=[...prev];next[next.length-1]={...next[next.length-1],content:next[next.length-1].content+payload.token};return next})}}
      refresh()
    }catch(e){setError(e instanceof Error?e.message:'生成回复失败');setMessages(prev=>prev[prev.length-1]?.content?prev:prev.slice(0,-1))}finally{setLoading(false);inputRef.current?.focus()}
  }
  const removeConversation=async(e:MouseEvent,id:string)=>{e.stopPropagation();try{await api('/api/conversations/'+id,{method:'DELETE'});if(active?.id===id){setActive(null);setMessages([])}refresh()}catch(err){setError(String(err))}}
  const toggleFavorite=async(e:MouseEvent,c:Conversation)=>{e.stopPropagation();try{await api(`/api/conversations/${c.id}/favorite`,{method:'PUT',body:JSON.stringify({enabled:!c.favorite})});refresh()}catch(err){setError(String(err))}}
  const changeMemory=async(enabled:boolean)=>{await api('/api/memories/enabled',{method:'PUT',body:JSON.stringify({enabled})});setMemoryEnabled(enabled)}

  return <div className="app-shell">
    {mobileNav&&<button className="scrim" onClick={()=>setMobileNav(false)} aria-label="关闭导航"/>}
    <aside className={`sidebar ${mobileNav?'sidebar-open':''}`}>
      <div className="brand"><div className="brand-mark"><span>e</span></div><div><strong>Eunoia</strong><small>倾听者</small></div><button className="icon-btn mobile-close" onClick={()=>setMobileNav(false)} aria-label="关闭"><X size={18}/></button></div>
      <button className="new-chat" onClick={startBlank}><Plus size={17}/> 新建对话 <span>⌘ N</span></button>
      <div className="nav-label">四个人格空间</div>
      <nav className="mode-nav">{modes.map(({id,label,icon:Icon,desc})=><button key={id} className={`nav-item ${currentMode===id?'selected':''}`} title={desc} onClick={()=>selectSpace(id)}><Icon size={17}/><span>{label}</span></button>)}</nav>
      <div className="nav-label advanced-label">自我理解</div>
      <button className="nav-item" onClick={()=>{setProfileOpen(true);setMobileNav(false)}}><Brain size={17}/><span>我的认知画像</span></button>
      <div className="history-heading"><span>最近对话</span><span>{conversations.length}</span></div>
      <div className="history-list">{conversations.map(c=><button key={c.id} className={`history-item ${active?.id===c.id?'current':''}`} onClick={()=>openConversation(c)}><MessageCircle size={15}/><span>{c.title}</span><span className="history-actions"><span onClick={e=>toggleFavorite(e,c)} title={c.favorite?'取消收藏':'收藏对话'}><Star size={13} fill={c.favorite?'currentColor':'none'}/></span><span className="delete-chat" onClick={e=>removeConversation(e,c.id)} title="删除对话"><Trash2 size={14}/></span></span></button>)}</div>
      <div className="sidebar-bottom"><button className="memory-link" onClick={()=>{setKnowledgeOpen(true);setMobileNav(false)}}><BookOpen size={17}/> 专业知识库</button><button className="memory-link" onClick={()=>{setMemOpen(true);refreshMemories()}}><ShieldCheck size={17}/> 本地记忆与隐私</button><div className="local-status"><span className={online?'status-dot online':'status-dot'}/>{online?'本地模型已连接':'等待 Ollama 连接'}</div></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><button className="icon-btn menu-toggle" onClick={()=>setMobileNav(true)} aria-label="打开导航"><span className="hamburger">☰</span></button><div className="crumb"><span>Eunoia——倾听者</span><span className="crumb-sep">/</span><span>{active?modes.find(m=>m.id===active.mode)?.label||'对话':modes.find(m=>m.id===selectedMode)?.label||'安静地，听你说'}</span></div><div className="top-actions"><div className={`connection ${online?'connected':''}`}><i/>{online?'本地运行':'未连接'}</div><div className="model-select"><Settings2 size={15}/><select value={model} onChange={e=>setModel(e.target.value)} aria-label="选择本地模型" disabled={!models.length}><option value="">选择模型</option>{models.map(m=><option key={m}>{m}</option>)}</select><ChevronDown size={13}/></div></div></header>
      <div className={`conversation-area ${messages.length?'has-messages':''}`}>
        {messages.length===0?<section className="welcome">
          <div className="portrait-wrap"><img className="portrait-art" src="/eunoia-avatar.jpg" alt="Eunoia 白发形象"/><span className="online-ring"/></div>
          <p className="eyebrow">一处留给自己的空间</p><h1>你好，我是 <em>{activePersona}</em></h1><p className="welcome-copy">{modes.find(m=>m.id===currentMode)?.welcome}</p>
          <div className="space-grid">{modes.map(({id,label,icon:Icon,desc})=><button key={id} className={currentMode===id?'selected':''} onClick={()=>selectSpace(id)}><Icon size={18}/><strong>{label}</strong><span>{desc}</span></button>)}</div>
        </section>:<section className="thread">{messages.map((m,i)=><article key={m.id??i} className={`message ${m.role}`}><div className={`avatar ${m.role==='assistant'?'eunoia-avatar':'user-avatar'}`}>{m.role==='assistant'?<img src="/eunoia-avatar.jpg" alt=""/>:'你'}</div><div className="message-content"><div className="message-meta">{m.role==='assistant'?activePersona:'你'}<span>{m.role==='assistant'?'· 陪你一起看':'· 刚刚'}</span></div><div className="message-text">{m.content||<span className="typing"><i/><i/><i/></span>}</div></div></article>)}<div ref={bottomRef}/></section>}
        {error&&<div className="error-note"><CircleHelp size={16}/>{error}</div>}
      </div>
      <div className="composer-wrap"><div className="composer">{currentMode==='debate'&&<div className="debate-styles" role="group" aria-label="辩论方式">{debateStyles.map(style=><button key={style.id} className={debateStyle===style.id?'active':''} aria-pressed={debateStyle===style.id} onClick={()=>setDebateStyle(style.id)}>{style.label}</button>)}</div>}<textarea ref={inputRef} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}} placeholder={currentMode==='debate'?'提出一个观点或问题，选择讨论方式后开始…':'把此刻的感受，慢慢说给我听…'} rows={2} disabled={loading}/><div className="composer-tools"><div className="composer-hint"><span><Leaf size={14}/> 不需要组织好语言</span><button className={`report-toggle ${report?'active':''}`} onClick={()=>setReport(!report)} title="生成结构化情感分析报告"><Brain size={14}/>{report?'深度报告已开启':'深度分析'}</button></div><button className="send-btn" disabled={!input.trim()||loading} onClick={()=>send()} aria-label="发送"><Send size={16}/></button></div></div><div className="disclaimer">Eunoia 是自我探索工具，不替代专业心理支持。你的对话仅保存在本机。</div></div>
    </main>

    {memOpen&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setMemOpen(false)}}><section className="memory-modal"><header><div><span className="panel-kicker">仅保存在此设备</span><h2>记忆与隐私</h2></div><button className="icon-btn" onClick={()=>setMemOpen(false)} aria-label="关闭"><X size={18}/></button></header><div className="memory-switch-row"><div><strong>允许使用长期记忆</strong><p>仅使用你保存的内容理解上下文，不会自动推断永久特征。</p></div><button role="switch" aria-checked={memoryEnabled} className={`switch ${memoryEnabled?'on':''}`} onClick={()=>changeMemory(!memoryEnabled)}><i/></button></div><div className="memory-list-title">已保存的记忆 <span>{memories.length}</span></div><div className="memory-list">{memories.length?memories.map(m=><div className="memory-row" key={m.id}><div><span className="memory-category">{m.category} · {m.kind==='fact'?'事实':m.kind==='hypothesis'?'推测':'自述'} · {Math.round(m.confidence*100)}%</span><p>{m.content}</p></div><button className="icon-btn" title="删除记忆" onClick={async()=>{await api('/api/memories/'+m.id,{method:'DELETE'});refreshMemories()}}><Trash2 size={15}/></button></div>):<div className="memory-empty">目前没有保存的记忆。你可以通过本地 API 添加和管理它们。</div>}</div><div className="privacy-foot"><ShieldCheck size={15}/> 对话和记忆保存在本地 SQLite，不会发送到云端。</div></section></div>}
    {memOpen&&<MemoryEditor onClose={()=>setMemOpen(false)}/>}
    {profileOpen&&<CognitiveProfile onClose={()=>setProfileOpen(false)}/>}
    {knowledgeOpen&&<KnowledgeManager onClose={()=>setKnowledgeOpen(false)}/>}
  </div>
}
