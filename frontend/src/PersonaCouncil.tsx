import { useState } from 'react'
import { UsersRound, X } from 'lucide-react'

const personas = [
  ['anatomy', 'Evelyn', '情感解剖'],
  ['debate', 'Arthur', '理性辩论'],
  ['guidance', 'Sophia', '生活指导'],
  ['self_exploration', 'Iris', '自我探索'],
  ['lucien', 'Lucien', '文学艺术'],
  ['felix', 'Felix', '日常闲谈'],
] as const

type Result = { persona_id: string; name: string; analysis: string; references: { title: string; source_path: string }[] }

export default function PersonaCouncil({ onClose }: { onClose: () => void }) {
  const [participants, setParticipants] = useState<string[]>(['anatomy', 'debate'])
  const [content, setContent] = useState('')
  const [results, setResults] = useState<Result[]>([])
  const [summary, setSummary] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const toggle = (id: string) => setParticipants(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])
  const consult = async () => {
    setError('')
    setResults([])
    setSummary('')
    setLoading(true)
    try {
      const response = await fetch('/api/persona-council', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, participants }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '联合会诊失败')
      setResults(data.results)
      setSummary(data.summary || '')
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : '联合会诊失败')
    } finally {
      setLoading(false)
    }
  }

  return <div className="council-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="council-panel" role="dialog" aria-modal="true" aria-labelledby="council-title">
      <header><div><span className="panel-kicker">由你决定 · 独立分析</span><h2 id="council-title"><UsersRound size={20}/> 联合会诊</h2><p>每个人格只使用自己的提示词、模型和知识库；不读取私人记忆，会诊内容不会写入普通对话。观点汇总使用第一位参与人格绑定的模型。</p></div><button className="icon-btn" onClick={onClose} aria-label="关闭"><X size={18}/></button></header>
      <div className="council-participants">{personas.map(([id, name, area]) => <label key={id} className={participants.includes(id) ? 'chosen' : ''}><input type="checkbox" checked={participants.includes(id)} onChange={() => toggle(id)}/><span><strong>{name}</strong><small>{area}</small></span></label>)}</div>
      <textarea className="council-input" value={content} onChange={event => setContent(event.target.value)} placeholder="描述你希望从多个角度理解的问题…" rows={4}/>
      <button className="council-submit" disabled={loading || content.trim().length === 0 || participants.length < 2} onClick={() => void consult()}>{loading ? '正在分别分析…' : `请 ${participants.length} 位人格独立分析`}</button>
      {error && <p className="council-error" role="alert">{error}</p>}
      {results.length > 0 && <section className="council-results" aria-live="polite">{results.map(result => <article key={result.persona_id}><h3>{result.name}</h3><p>{result.analysis}</p>{result.references?.length > 0 && <small>参考了该人格知识库：{result.references.map(item => item.title).join('、')}</small>}</article>)}{summary&&<article><h3>观点汇总</h3><p>{summary}</p></article>}</section>}
    </section>
  </div>
}
