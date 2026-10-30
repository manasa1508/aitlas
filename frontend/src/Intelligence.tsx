import { useEffect, useState, type ReactNode } from 'react'
import { api, type IntelligenceData, type Signal } from './api'

export default function Intelligence({ renderItem }: { renderItem: (item: Signal) => ReactNode }) {
  const [data, setData] = useState<IntelligenceData | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('Discoveries')
  const [days, setDays] = useState(7)
  const [topic, setTopic] = useState('all')
  useEffect(() => {
    let active = true
    async function load() {
      try { const result = await api<IntelligenceData>(`/intelligence?days=${days}&topic=${encodeURIComponent(topic)}`); if (active) { setData(result); setError('') } }
      catch { if (active) setError('Could not refresh intelligence. Any displayed results are from the previous refresh.') }
    }
    setData(null); void load()
    const timer = window.setInterval(() => { if (!document.hidden) void load() }, 60_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [days, topic])
  return <>
    <div className="page-heading"><div><span className="eyebrow">LEARN / ADAPT / EVOLVE</span><h1>AI intelligence<span className="accent-dot">.</span></h1><p>Research discoveries, measured attention, reported technology shifts and market coverage. Open the original evidence before acting on a claim.</p></div></div>
    <div className="filters"><div className="segmented">{['Discoveries', 'Trends', 'Top repos', 'Technology shifts', 'Markets'].map(value => <button key={value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{value}</button>)}</div><label className="select-wrap">Window <select aria-label="Intelligence time window" value={days} onChange={e => setDays(Number(e.target.value))}>{[1, 7, 30].map(value => <option value={value} key={value}>Last {value === 1 ? '24 hours' : `${value} days`}</option>)}</select></label></div>
    {error && <div className="error-banner">{error}</div>}
    {data && <>
      <div className="filters"><label className="select-wrap">Topic <select aria-label="Intelligence topic" value={topic} onChange={e => setTopic(e.target.value)}><option value="all">All topics</option>{data.topics.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label><span className="filter-count">{data.sample_size} sampled records{data.sample_truncated ? ' · sample limit reached' : ''}</span></div>
      <p className="methodology">{data.methodology}</p>
      {tab === 'Discoveries' && (data.discoveries.length ? <div className="signal-grid">{data.discoveries.map(renderItem)}</div> : <p>No research records in this window. Try a wider window.</p>)}
      {tab === 'Trends' && <div className="company-grid">{data.topics.map(row => <article className="signal-card" key={row.id}><span className="category-tag">Indexed attention</span><h3>{row.name}</h3><p>{row.count} matching records across {row.source_count} sources in this window; {row.previous_count} in the preceding equally sized window. Topics can overlap.</p><button className="ghost-button" onClick={() => { setTopic(row.id); setTab('Discoveries') }}>Explore evidence</button></article>)}</div>}
      {tab === 'Top repos' && <><p className="methodology">Repositories with at least 25 stars, ordered by observed star count. Repository dates show latest pushed activity; original creation dates appear in details. Stars do not measure code safety or quality.</p>{data.repos.length ? <div className="signal-grid">{data.repos.map(renderItem)}</div> : <p>No qualifying repositories in this window.</p>}</>}
      {tab === 'Technology shifts' && (data.shifts.length ? <div className="signal-grid">{data.shifts.map(row => <article className="signal-card" key={row.item.id}><span className="category-tag">{row.label}</span><h3><a href={row.item.url} target="_blank" rel="noopener noreferrer">{row.item.title}</a></h3><p>{row.claim_excerpt}</p><div className="methodology">{row.status}. A comparison does not establish that a technology is obsolete. Review task, benchmark, cost, license and migration compatibility.</div><small>{row.item.source} · {new Date(row.item.published_at).toLocaleDateString()}</small></article>)}</div> : <p>No explicit comparison or migration claims were found in this window.</p>)}
      {tab === 'Markets' && <><div className="freshness-note"><p><strong>Reported market context.</strong> Price quotes are not connected. These are company mentions and publisher-reported market reactions, not verified price moves or proof of causation. Quote links open an external provider.</p></div><div className="company-grid intelligence-markets">{data.markets.map(row => <article className="signal-card" key={row.symbol}><span className="category-tag">{row.symbol}</span><h3>{row.name}</h3><p>{row.news_count} matching articles · {row.reaction_reports.length} displayed market-reaction reports</p>{(row.reaction_reports.length ? row.reaction_reports : row.reports).map(item => <a className="intelligence-link" href={item.url} key={item.id} target="_blank" rel="noopener noreferrer">{item.title}<small>{item.source} · {new Date(item.published_at).toLocaleDateString()}</small></a>)}<a className="source-link" href={row.quote_url} target="_blank" rel="noopener noreferrer">View external market data ↗</a></article>)}</div></>}
    </>}
    {!data && !error && <p>Loading current intelligence…</p>}
  </>
}
