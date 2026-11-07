import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { BookOpen, Brain, CircleHelp, Coffee, Compass, Heart, Leaf, MessageCircle, Palette, Plus, Send, Settings2, ShieldCheck, Sparkles, Star, Trash2, UsersRound, X } from 'lucide-react'
import MemoryEditor from './MemoryEditor'
import CognitiveProfile from './CognitiveProfile'
import KnowledgeManager from './KnowledgeManager'
import ModelManager from './ModelManager'
import PersonaCouncil from './PersonaCouncil'
import ListeningSpace from './ListeningSpace'
import './v4.css'

type Mode = 'anatomy'|'debate'|'guidance'|'self_exploration'|'lucien'|'felix'
type DebateStyle = 'discussion'|'opposition'|'steelman'|'both_sides'
type Conversation = { id: string; title: string; mode: Mode; preview?: string; favorite?: number|boolean }
type Message = { id?: number|string; role: 'user'|'assistant'; content: string; analysis_json?: string|null }

const modes: { id: Mode; label: string; persona: string; icon: typeof Heart; desc: string; welcome: string }[] = [
  { id:'anatomy', label:'情感解剖', persona:'Evelyn', icon:Heart, desc:'温柔剖析情绪，探寻情感深处的真实。', welcome:'我想听见，你沉默背后的声音。' },
  { id:'debate', label:'理性辩论', persona:'Arthur', icon:Sparkles, desc:'以逻辑审视观点，以理性接近真相。', welcome:'质疑一切，唯独不放弃思考。' },
  { id:'guidance', label:'生活指导', persona:'Sophia', icon:Compass, desc:'洞察现实困境，寻找切实可行的出路。', welcome:'人生的答案，要自己走出来。' },
  { id:'self_exploration', label:'自我探索', persona:'Iris', icon:Brain, desc:'向内探索自我，理解存在与成长。', welcome:'向内凝视，看见真实的自己。' },
  { id:'lucien', label:'文学艺术', persona:'Lucien', icon:Palette, desc:'漫游文学与艺术，在作品中发现新的感受。', welcome:'作品不急着给出答案，它先让我们看见。' },
  { id:'felix', label:'日常闲谈', persona:'Felix', icon:Coffee, desc:'聊聊兴趣、流行文化和今天遇见的小事。', welcome:'生活已经够复杂了，先聊点有意思的。' },
]
const personaNames: Record<Mode,string> = { anatomy:'Evelyn', debate:'Arthur', guidance:'Sophia', self_exploration:'Iris', lucien:'Lucien', felix:'Felix' }
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
  const [home,setHome] = useState(true)
  const [messages,setMessages] = useState<Message[]>([])
  const [input,setInput] = useState('')
  const [modelReady,setModelReady] = useState(false)
  const [hasAnyModel,setHasAnyModel] = useState(false)
  const [online,setOnline] = useState(false)
  const [loading,setLoading] = useState(false)
  const [report,setReport] = useState(false)
  const [debateStyle,setDebateStyle] = useState<DebateStyle>('discussion')
  const [error,setError] = useState('')
  const [memOpen,setMemOpen] = useState(false)
  const [mobileNav,setMobileNav] = useState(false)
  const [profileOpen,setProfileOpen] = useState(false)
  const [knowledgeOpen,setKnowledgeOpen] = useState(false)
  const [modelManagerOpen,setModelManagerOpen] = useState(false)
  const [councilOpen,setCouncilOpen] = useState(false)
  const [listeningOpen,setListeningOpen] = useState(false)
  const currentMode = active?.mode || selectedMode
  const currentSpace = modes.find(m=>m.id===currentMode) || modes[2]
  const activePersona = personaNames[currentMode] || 'Eunoia'
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamRef = useRef<AbortController | null>(null)

  const refresh = async () => { try { setConversations(await api<Conversation[]>('/api/conversations')) } catch { /* backend may still be starting */ } }
  const refreshModelStatus=async()=>{try{const data=await api<{configs:{id:string;enabled:boolean}[];assignments:Record<string,string|null>;default_config_id:string|null}>('/api/model-configs');const usable=data.configs.some(config=>config.enabled);setHasAnyModel(usable);setModelReady(Boolean(data.assignments[currentMode]||data.default_config_id));setOnline(usable)}catch{setOnline(false);setModelReady(false)}}
  useEffect(()=>{refresh();void refreshModelStatus();const timer=setInterval(()=>{void refreshModelStatus()},8000);return()=>clearInterval(timer)},[])
  useEffect(()=>{void refreshModelStatus()},[currentMode])
  useEffect(()=>{bottomRef.current?.scrollIntoView({behavior:'smooth'})},[messages])

  const stopStream = () => { streamRef.current?.abort();streamRef.current=null;setLoading(false) }
  const openConversation = async (c: Conversation) => { stopStream();setError('');try { const d=await api<{messages:Message[]}>('/api/conversations/'+c.id);setActive(c);setSelectedMode(c.mode);setHome(false);setMessages(d.messages);setMobileNav(false) } catch(e){setError(String(e))} }
  const selectSpace = (mode: Mode) => { stopStream();setActive(null);setSelectedMode(mode);setHome(false);setMessages([]);setInput('');setError('');setMobileNav(false) }
  const returnHome = () => { stopStream();setActive(null);setHome(true);setMessages([]);setInput('');setError('');setMobileNav(false) }
  const startBlank = () => { stopStream();setActive(null);setMessages([]);setInput('');setError('');setMobileNav(false) }
  const send = async (text=input) => {
    const content=text.trim();if(home||!content||loading)return
    try{const config=await api<{assignments:Record<string,string|null>;default_config_id:string|null}>('/api/model-configs');if(!config.assignments[currentMode]&&!config.default_config_id){setError('该人格还没有绑定模型，请先完成模型配置。');setModelManagerOpen(true);return}}catch{setError('本地服务暂不可用，无法检查模型配置。');return}
    let target=active
    if(!target){try{target=await api<Conversation>('/api/conversations',{method:'POST',body:JSON.stringify({mode:selectedMode})});setActive(target);refresh()}catch(e){setError(String(e));return}}
    setInput('');setError('');setLoading(true);setReport(false)
    setMessages(prev=>[...prev,{role:'user',content},{role:'assistant',content:''}])
    const controller = new AbortController()
    streamRef.current = controller
    try {
      const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({conversation_id:target.id,content,mode:target.mode,deep_report:report,debate_style:target.mode==='debate'?debateStyle:undefined})})
      if(!response.ok||!response.body){const issue=await response.json().catch(()=>({detail:'无法连接本地服务，请确认后端已启动。'}));throw new Error(issue.detail||'模型请求失败。')}
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer=''
      while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const events=buffer.split('\n\n');buffer=events.pop()||'';for(const event of events){const data=event.split('\n').find(line=>line.startsWith('data: '))?.slice(6);if(!data)continue;const payload=JSON.parse(data);if(event.includes('event: error'))throw new Error(payload.message);if(payload.token&&streamRef.current===controller)setMessages(prev=>{const next=[...prev];next[next.length-1]={...next[next.length-1],content:next[next.length-1].content+payload.token};return next})}}
      if(streamRef.current===controller)refresh()
    }catch(e){if(streamRef.current===controller){setError(e instanceof Error?e.message:'生成回复失败');setMessages(prev=>prev[prev.length-1]?.content?prev:prev.slice(0,-1))}}finally{if(streamRef.current===controller){streamRef.current=null;setLoading(false);inputRef.current?.focus()}}
  }
  const removeConversation=async(e:MouseEvent,id:string)=>{e.stopPropagation();try{await api('/api/conversations/'+id,{method:'DELETE'});if(active?.id===id){setActive(null);setMessages([])}refresh()}catch(err){setError(String(err))}}
  const toggleFavorite=async(e:MouseEvent,c:Conversation)=>{e.stopPropagation();try{await api(`/api/conversations/${c.id}/favorite`,{method:'PUT',body:JSON.stringify({enabled:!c.favorite})});refresh()}catch(err){setError(String(err))}}

  if(listeningOpen)return <ListeningSpace onBack={()=>setListeningOpen(false)} onModelManage={()=>{setListeningOpen(false);setModelManagerOpen(true)}}/>

  return <div className="app-shell">
    {mobileNav&&<button className="scrim" onClick={()=>setMobileNav(false)} aria-label="关闭导航"/>}
    <aside className={`sidebar ${mobileNav?'sidebar-open':''}`}>
      <div className="brand"><button className="brand-home" onClick={returnHome} aria-label="返回首页"><div className="brand-mark"><span>e</span></div><strong>Eunoia</strong></button><button className="icon-btn mobile-close" onClick={()=>setMobileNav(false)} aria-label="关闭"><X size={18}/></button></div>
      {!home&&<button className="new-chat" onClick={startBlank}><Plus size={17}/> 新建对话 <span>⌘ N</span></button>}
      <div className="nav-label">六个人格空间</div>
      <nav className="mode-nav">{modes.map(({id,label,icon:Icon,desc})=><button key={id} className={`nav-item ${!home&&currentMode===id?'selected':''}`} title={desc} onClick={()=>selectSpace(id)}><Icon size={17}/><span>{label}</span></button>)}</nav>
      <div className="nav-label advanced-label">独立倾听</div><button className="nav-item haven-nav" onClick={()=>{stopStream();setListeningOpen(true);setMobileNav(false)}}><Leaf size={17}/><span>倾听空间</span></button>
      <div className="nav-label advanced-label">自我理解</div>
      <button className="nav-item" onClick={()=>{setProfileOpen(true);setMobileNav(false)}}><Brain size={17}/><span>我的认知画像</span></button>
      <button className="nav-item" onClick={()=>{setCouncilOpen(true);setMobileNav(false)}}><UsersRound size={17}/><span>联合会诊</span></button>
      <div className="history-heading"><span>最近对话</span><span>{conversations.length}</span></div>
      <div className="history-list">{conversations.map(c=><button key={c.id} className={`history-item ${active?.id===c.id?'current':''}`} onClick={()=>openConversation(c)}><MessageCircle size={15}/><span>{c.title}</span><span className="history-actions"><span onClick={e=>toggleFavorite(e,c)} title={c.favorite?'取消收藏':'收藏对话'}><Star size={13} fill={c.favorite?'currentColor':'none'}/></span><span className="delete-chat" onClick={e=>removeConversation(e,c.id)} title="删除对话"><Trash2 size={14}/></span></span></button>)}</div>
      <div className="sidebar-bottom"><button className="memory-link" onClick={()=>{setKnowledgeOpen(true);setMobileNav(false)}}><BookOpen size={17}/> 专业知识库</button><button className="memory-link" onClick={()=>{setModelManagerOpen(true);setMobileNav(false)}}><Settings2 size={17}/> 模型管理</button><button className="memory-link" onClick={()=>setMemOpen(true)}><ShieldCheck size={17}/> 本地记忆与隐私</button><div className="local-status"><span className={online?'status-dot online':'status-dot'}/>{online?'已配置用户模型':'等待用户配置模型'}</div></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><button className="icon-btn menu-toggle" onClick={()=>setMobileNav(true)} aria-label="打开导航"><span className="hamburger">☰</span></button><div className="crumb"><span>Eunoia</span><span className="crumb-sep">/</span><span>{home?'首页':active?modes.find(m=>m.id===active.mode)?.label||'对话':modes.find(m=>m.id===selectedMode)?.label||'对话'}</span></div><div className="top-actions"><div className={`connection ${online?'connected':''}`}><i/>{online?'已配置模型':'未配置模型'}</div><button className="model-manager-trigger" onClick={()=>setModelManagerOpen(true)}><Settings2 size={15}/>模型管理</button></div></header>
      <div className={`conversation-area ${messages.length?'has-messages':''}`}>
        {home?<section className="welcome home-welcome">
          {!hasAnyModel&&<section className="model-onboarding"><strong>欢迎使用 Eunoia。</strong><p>Eunoia 不提供内置 AI 模型服务。你需要自行申请第三方模型 API，并在模型管理中完成配置。</p><button onClick={()=>setModelManagerOpen(true)}><Settings2 size={15}/>前往模型配置</button></section>}
          <div className="portrait-wrap"><img className="portrait-art" src="/eunoia-avatar.jpg" alt="Eunoia 白发形象"/><span className="online-ring"/></div>
          <h1>欢迎回来</h1>
          <div className="space-grid">{modes.map(({id,label,icon:Icon,desc})=><button key={id} onClick={()=>selectSpace(id)}><Icon size={18}/><strong>{label}</strong><span>{desc}</span></button>)}</div>
        </section>:messages.length===0?<section className="welcome">
          {!hasAnyModel&&<section className="model-onboarding"><strong>欢迎使用 Eunoia。</strong><p>Eunoia 不提供内置 AI 模型服务。你需要自行申请第三方模型 API，并在模型管理中完成配置。</p><p>配置完成后，即可开启你的六人格探索之旅。</p><button onClick={()=>setModelManagerOpen(true)}><Settings2 size={15}/>前往模型配置</button></section>}
          {hasAnyModel&&!modelReady&&<section className="model-onboarding compact"><p>当前人格尚未绑定模型。请在模型管理中选择已接入的模型，或设置全局默认模型。</p><button onClick={()=>setModelManagerOpen(true)}><Settings2 size={15}/>绑定模型</button></section>}
          <div className="portrait-wrap"><img className="portrait-art" src="/eunoia-avatar.jpg" alt="Eunoia 白发形象"/><span className="online-ring"/></div>
          <p className="eyebrow">一处留给自己的空间</p><h1>你好，我是 <em>{activePersona}</em></h1><p className="welcome-copy">{currentSpace.welcome}</p>
        </section>:<section className="thread">{messages.map((m,i)=><article key={m.id??i} className={`message ${m.role}`}><div className={`avatar ${m.role==='assistant'?'eunoia-avatar':'user-avatar'}`}>{m.role==='assistant'?<img src="/eunoia-avatar.jpg" alt=""/>:'你'}</div><div className="message-content"><div className="message-meta">{m.role==='assistant'?activePersona:'你'}<span>{m.role==='assistant'?'· 陪你一起看':'· 刚刚'}</span></div><div className="message-text">{m.content||<span className="typing"><i/><i/><i/></span>}</div></div></article>)}<div ref={bottomRef}/></section>}
        {error&&<div className="error-note"><CircleHelp size={16}/>{error}</div>}
      </div>
      {!home&&<div className="composer-wrap"><div className="composer">{currentMode==='debate'&&<div className="debate-styles" role="group" aria-label="辩论方式">{debateStyles.map(style=><button key={style.id} className={debateStyle===style.id?'active':''} aria-pressed={debateStyle===style.id} onClick={()=>setDebateStyle(style.id)}>{style.label}</button>)}</div>}<textarea ref={inputRef} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}} placeholder={currentMode==='debate'?'提出一个观点或问题，选择讨论方式后开始…':currentMode==='lucien'?'想聊一部作品、一种艺术，或某段创作灵感…':currentMode==='felix'?'最近在看什么、玩什么，或者今天发生了什么？':'把此刻的感受，慢慢说给我听…'} rows={2} disabled={loading}/><div className="composer-tools"><div className="composer-hint"><span><Leaf size={14}/> 不需要组织好语言</span>{currentMode!=='lucien'&&currentMode!=='felix'&&<button className={`report-toggle ${report?'active':''}`} onClick={()=>setReport(!report)} title="生成结构化情感分析报告"><Brain size={14}/>{report?'深度报告已开启':'深度分析'}</button>}</div><button className="send-btn" disabled={!input.trim()||loading} onClick={()=>send()} aria-label="发送"><Send size={16}/></button></div></div><div className="disclaimer">Eunoia 是自我探索工具，不替代专业心理支持。你的对话仅保存在本机。</div></div>}
    </main>

    {memOpen&&<MemoryEditor persona={currentMode} onClose={()=>setMemOpen(false)}/>}
    {profileOpen&&<CognitiveProfile persona={currentMode} onClose={()=>setProfileOpen(false)} onCouncil={()=>{setProfileOpen(false);setCouncilOpen(true)}}/>}
    {knowledgeOpen&&<KnowledgeManager onClose={()=>setKnowledgeOpen(false)}/>}
    {modelManagerOpen&&<ModelManager onClose={()=>setModelManagerOpen(false)} onChanged={()=>{void refreshModelStatus()}}/>}
    {councilOpen&&<PersonaCouncil onClose={()=>setCouncilOpen(false)}/>}
  </div>
}
