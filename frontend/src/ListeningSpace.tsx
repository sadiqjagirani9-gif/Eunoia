import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Heart, MessageCircle, Plus, Send, Settings2, ShieldCheck, Trash2 } from 'lucide-react'
import './listening.css'

type Conversation={id:string;title:string;preview?:string}
type Message={id?:number;role:'user'|'assistant';content:string}
type Memory={id:string;content:string}
type Settings={memory_enabled:boolean;model_config_id:string|null}
type Model={id:string;name:string;model_id:string;enabled:boolean}
const recipients=[['anatomy','Evelyn'],['debate','Arthur'],['guidance','Sophia'],['self_exploration','Iris'],['lucien','Lucien'],['felix','Felix']]

async function request<T>(path:string,init?:RequestInit):Promise<T>{
  const response=await fetch('/api/listening'+path,{...init,headers:{'Content-Type':'application/json',...init?.headers}})
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||'操作失败')}
  return response.json()
}
const json=(method:string,body:unknown):RequestInit=>({method,body:JSON.stringify(body)})

export default function ListeningSpace({onBack,onModelManage}:{onBack:()=>void;onModelManage:()=>void}){
  const [conversations,setConversations]=useState<Conversation[]>([])
  const [active,setActive]=useState<Conversation|null>(null)
  const [messages,setMessages]=useState<Message[]>([])
  const [input,setInput]=useState('')
  const [settings,setSettings]=useState<Settings>({memory_enabled:false,model_config_id:null})
  const [models,setModels]=useState<Model[]>([])
  const [memories,setMemories]=useState<Memory[]>([])
  const [memoryDraft,setMemoryDraft]=useState('')
  const [editing,setEditing]=useState<string|null>(null)
  const [transferId,setTransferId]=useState<number|null>(null)
  const [recipient,setRecipient]=useState('anatomy')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const controller=useRef<AbortController|null>(null)
  const bottom=useRef<HTMLDivElement|null>(null)
  const refresh=async()=>{const [history,configuration,saved,available]=await Promise.all([
    request<Conversation[]>('/conversations'),request<Settings>('/settings'),request<Memory[]>('/memories'),
    fetch('/api/model-configs').then(r=>r.json()).then(data=>data.configs as Model[]),
  ]);setConversations(history);setSettings(configuration);setMemories(saved);setModels(available.filter(item=>item.enabled))}
  useEffect(()=>{void refresh().catch(issue=>setError(String(issue)));return()=>controller.current?.abort()},[])
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'})},[messages])
  const reset=()=>{controller.current?.abort();controller.current=null;setBusy(false);setActive(null);setMessages([]);setInput('');setError('');setNotice('')}
  const openPrivacy=()=>{const panel=document.getElementById('haven-privacy') as HTMLDetailsElement|null;if(panel){panel.open=true;panel.scrollIntoView({behavior:'smooth'})}}
  const open=async(item:Conversation)=>{reset();try{const result=await request<{conversation:Conversation;messages:Message[]}>(`/conversations/${item.id}`);setActive(result.conversation);setMessages(result.messages)}catch(issue){setError(String(issue))}}
  const send=async()=>{
    const content=input.trim();if(!content||busy)return
    if(!settings.model_config_id){setError('请先为 Haven 选择已接入的模型。');openPrivacy();return}
    let conversation=active
    try{if(!conversation){conversation=await request<Conversation>('/conversations',{method:'POST'});setActive(conversation);void refresh()}}catch(issue){setError(String(issue));return}
    setInput('');setError('');setBusy(true);setMessages(rows=>[...rows,{role:'user',content},{role:'assistant',content:''}])
    const abort=new AbortController();controller.current=abort
    try{
      const response=await fetch('/api/listening/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:conversation.id,content}),signal:abort.signal})
      if(!response.ok||!response.body){const body=await response.json().catch(()=>({}));throw new Error(body.detail||'无法连接 Haven')}
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer=''
      while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let boundary=buffer.indexOf('\n\n');while(boundary>=0){const event=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const line=event.split('\n').find(part=>part.startsWith('data: '));if(line){const data=JSON.parse(line.slice(6));if(data.token)setMessages(rows=>rows.map((row,index)=>index===rows.length-1?{...row,content:row.content+data.token}:row));if(data.error)throw new Error(data.error)}boundary=buffer.indexOf('\n\n')}}
      try{const result=await request<{conversation:Conversation;messages:Message[]}>(`/conversations/${conversation.id}`);if(controller.current===abort)setMessages(result.messages)}catch{/* streamed answer remains visible */}
      void refresh()
    }catch(issue){if(!abort.signal.aborted){setError(String(issue));setMessages(rows=>rows[rows.length-1]?.content?rows:rows.slice(0,-1))}}
    finally{if(controller.current===abort){controller.current=null;setBusy(false)}}
  }
  const remove=async(id:string)=>{if(!window.confirm('删除这段倾听对话？'))return;try{await request(`/conversations/${id}`,{method:'DELETE'});if(active?.id===id)reset();await refresh()}catch(issue){setError(String(issue))}}
  const saveMemory=async()=>{if(!memoryDraft.trim())return;try{await request(editing?`/memories/${editing}`:'/memories',json(editing?'PATCH':'POST',{content:memoryDraft.trim()}));setMemoryDraft('');setEditing(null);await refresh()}catch(issue){setError(String(issue))}}
  const transfer=async()=>{if(!active||transferId===null)return;try{await request('/transfer',json('POST',{conversation_id:active.id,message_id:transferId,recipient}));setNotice(`已将所选内容单次转交给 ${recipients.find(item=>item[0]===recipient)?.[1]}。`);setTransferId(null)}catch(issue){setError(String(issue))}}
  return <div className="listening-shell">
    <aside className="listening-sidebar"><div className="listening-brand"><span className="haven-mark">H</span><div><strong>Haven</strong><small>倾听空间</small></div></div><button className="listening-back" onClick={onBack}><ArrowLeft size={16}/>返回六人格空间</button><button className="listening-new" onClick={reset}><Plus size={16}/>新的倾听对话</button><div className="listening-history-title">倾听记录 <span>{conversations.length}</span></div><div className="listening-history">{conversations.map(item=><div key={item.id} className={active?.id===item.id?'current':''}><button onClick={()=>void open(item)}><MessageCircle size={14}/>{item.title}</button><button aria-label="删除倾听对话" onClick={()=>void remove(item.id)}><Trash2 size={14}/></button></div>)}</div><div className="listening-sidebar-foot"><button onClick={openPrivacy}><ShieldCheck size={15}/>记忆与隐私</button></div></aside>
    <main className="listening-main"><header className="listening-topbar"><span>Haven / 倾听空间</span><div className="listening-mobile-actions"><button onClick={reset}><Plus size={14}/>新对话</button><details><summary>历史</summary><div>{conversations.map(item=><button key={item.id} onClick={()=>void open(item)}>{item.title}</button>)}</div></details></div><button onClick={onBack}><ArrowLeft size={14}/>返回</button></header><div className="listening-scroll">
      {messages.length===0?<section className="listening-welcome"><div className="haven-avatar"><Heart size={30}/></div><span className="listening-kicker">一处安静的地方</span><h1>I believe in you.</h1><p>你可以慢慢说，也可以只是待一会儿。Haven 会认真听。</p><blockquote>I am always there waiting for you.</blockquote></section>:<section className="listening-thread">{messages.map((item,index)=><article key={item.id??index} className={`listening-message ${item.role}`}><div className="listening-message-avatar">{item.role==='assistant'?'H':'你'}</div><div><strong>{item.role==='assistant'?'Haven':'你'}</strong><p>{item.content||'…'}</p>{item.role==='user'&&item.id&&<button className="listening-transfer-trigger" onClick={()=>setTransferId(item.id!)}>单次转交这条消息</button>}</div></article>)}<div ref={bottom}/></section>}
      {transferId!==null&&<div className="listening-transfer"><strong>只转交这条由你发送的消息</strong><p>接收人格会在新对话中看到这条原文；不会获得 Haven 的其他记录或记忆。</p><select value={recipient} onChange={event=>setRecipient(event.target.value)}>{recipients.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select><button onClick={()=>void transfer()}>确认转交</button><button onClick={()=>setTransferId(null)}>取消</button></div>}
      {notice&&<p className="listening-notice">{notice}</p>}{error&&<p className="listening-error" role="alert">{error}</p>}
    </div><div className="listening-composer"><textarea value={input} onChange={event=>setInput(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();void send()}}} placeholder="想说什么都可以。" disabled={busy} rows={2}/><div><span>你不必整理好情绪。</span><button onClick={()=>void send()} disabled={!input.trim()||busy} aria-label="发送给 Haven"><Send size={17}/></button></div></div>
    <details className="listening-privacy" id="haven-privacy"><summary><ShieldCheck size={17}/>记忆与隐私</summary><p>Haven 不参与认知画像、知识检索或联合会诊。这里的对话与记忆独立保存在本机。选择云端模型后，对话会发送到你配置的服务商。</p><label>Haven 使用的模型 <select value={settings.model_config_id||''} onChange={event=>void request<Settings>('/model',json('PUT',{config_id:event.target.value||null})).then(setSettings).catch(issue=>setError(String(issue)))}><option value="">请选择模型</option>{models.map(item=><option key={item.id} value={item.id}>{item.name} · {item.model_id}</option>)}</select></label><button onClick={onModelManage}><Settings2 size={14}/>管理已接入模型</button><label className="listening-memory-toggle"><input type="checkbox" checked={settings.memory_enabled} onChange={event=>void request<Settings>('/memories/enabled',json('PUT',{enabled:event.target.checked})).then(setSettings).catch(issue=>setError(String(issue)))}/>启用 Haven 记忆（默认关闭）</label><p>仅保存你亲自填写的内容。关闭后停止读取和写入；已有记忆仍可删除。</p>{settings.memory_enabled&&<div className="listening-memory-form"><textarea value={memoryDraft} onChange={event=>setMemoryDraft(event.target.value)} placeholder="只写下你希望 Haven 记住的事" maxLength={1000}/><button onClick={()=>void saveMemory()} disabled={!memoryDraft.trim()}>{editing?'保存修改':'保存记忆'}</button></div>}{memories.map(item=><div className="listening-memory" key={item.id}><span>{item.content}</span><div><button disabled={!settings.memory_enabled} onClick={()=>{setEditing(item.id);setMemoryDraft(item.content)}}>修改</button><button onClick={()=>void request(`/memories/${item.id}`,{method:'DELETE'}).then(refresh).catch(issue=>setError(String(issue)))}>删除</button></div></div>)}<div className="listening-danger"><button onClick={()=>{if(window.confirm('清除全部倾听对话？'))void request('/history',{method:'DELETE'}).then(()=>{reset();return refresh()}).catch(issue=>setError(String(issue)))}}>清除全部倾听对话</button><button onClick={()=>{if(window.confirm('清除全部 Haven 记忆？'))void request('/memories',{method:'DELETE'}).then(refresh).catch(issue=>setError(String(issue)))}}>清除全部倾听记忆</button></div></details></main>
  </div>
}
