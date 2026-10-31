import { useEffect, useState } from 'react'
import { api, type EmployerResponse } from './api'

export default function EmployerDirectory({ city, role = 'all', aiOnly, onSelect }: { city: string; role?: string; aiOnly: boolean; onSelect: (name: string) => void }) {
  const [data, setData] = useState<EmployerResponse | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [coverage, setCoverage] = useState('public_feed')
  const [category, setCategory] = useState('all')
  const [recognition, setRecognition] = useState('all')
  const [discovery, setDiscovery] = useState('all')
  useEffect(() => {
    let active = true
    setData(null); setError('')
    async function load() {
      try { const result = await api<EmployerResponse>(`/employers?city=${city}&role=${encodeURIComponent(role)}&ai_only=${aiOnly}`); if (active) { setData(result); setError('') } }
      catch { if (active) setError('Employer coverage could not be refreshed. Any displayed counts are from the last successful refresh.') }
    }
    void load(); const timer = window.setInterval(() => { if (!document.hidden) void load() }, 60_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [city, role, aiOnly])
  const employers = data?.employers.filter(row => row.name.toLowerCase().includes(query.toLowerCase()) && (coverage === 'all' || row.coverage === coverage) && (category === 'all' || row.category === category) && (recognition === 'all' || row.recognitions?.some(entry => entry.kind === recognition)) && (discovery === 'all' || row.discovery_sources?.some(entry => entry.id === discovery))) || []
  const summary = data?.coverage_summary
  return <section className="source-panel"><h3>India employer watchlist</h3>
    {summary && <div className="coverage-summary"><strong>{summary.connected_employers} connected employers</strong><span>{summary.career_links_only} careers links only</span><span>{summary.matching_roles} indexed roles under the city, role and AI filters</span><small>{summary.synced_employers} feeds have synced · {summary.failing_employers} need attention</small></div>}
    <p className="methodology">{data?.rating_status} Connected feeds supply searchable jobs. Careers links do not supply listings to AItlas. Verify office, team, eligibility and availability on the original posting.</p>
    {!!data?.discovery_sources?.length && <details className="methodology"><summary>Company discovery references</summary><p>Directories help identify employers. A directory mention does not verify hiring, office availability, Fortune membership or workplace quality. Vacancies come from the connected employer boards.</p>{data.discovery_sources.map(source => <p key={source.id}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a> · {source.status === 'reviewed' ? 'reviewed for company names' : 'unavailable; no entries imported'} · {source.checked_at}</p>)}</details>}
    <div className="job-tools"><input className="directory-search" aria-label="Search employers" placeholder="Find an employer…" value={query} onChange={e => setQuery(e.target.value)} />
      <label className="select-wrap">Coverage <select aria-label="Employer coverage" value={coverage} onChange={e => setCoverage(e.target.value)}><option value="public_feed">Indexed job feeds</option><option value="official_link">Careers links only</option><option value="all">All employers</option></select></label>
      <label className="select-wrap">Category <select aria-label="Employer category" value={category} onChange={e => setCategory(e.target.value)}><option value="all">All categories</option>{[...new Set(data?.employers.map(row => row.category) || [])].sort().map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="select-wrap">Evidence <select aria-label="Employer recognition" value={recognition} onChange={e => setRecognition(e.target.value)}><option value="all">All employers</option><option value="fortune500">Cited Fortune 500 membership</option><option value="workplace">Cited workplace award</option></select></label>
      <label className="select-wrap">Directory <select aria-label="Employer discovery directory" value={discovery} onChange={e => setDiscovery(e.target.value)}><option value="all">All discovery sources</option>{data?.discovery_sources?.filter(source => source.status === 'reviewed').map(source => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>
    </div>
    {error && <p className="error-text">{error}</p>}
    <div className="company-grid">{employers.map(row => <article className="signal-card" key={row.name}><span className="category-tag">{row.category}</span><h3>{row.name}</h3>{row.sector && <p>{row.sector}</p>}
      {row.coverage === 'public_feed' ? <><p>{row.open_roles} indexed matching roles{row.last_checked ? ` · checked ${new Date(row.last_checked).toLocaleString()}` : ' · awaiting first sync'}</p>{row.last_error && <p className="error-text">Refresh failed; the last indexed roles may be stale.</p>}<p>{row.locations.join(' · ')}</p><button className="ghost-button" onClick={() => onSelect(row.name)}>View matching jobs</button></> : <><p>Official careers link · listings are not indexed here</p><button className="ghost-button" onClick={() => onSelect(row.name)}>Search job boards for employer</button></>}
      {row.recognitions?.map(entry => <a className="intelligence-link" key={`${entry.kind}-${entry.year}`} href={entry.source_url} target="_blank" rel="noopener noreferrer">{entry.label} · {entry.year} ↗</a>)}
      {!!row.discovery_sources?.length && <details className="methodology"><summary>Listed in {row.discovery_sources.length} discovery {row.discovery_sources.length === 1 ? 'reference' : 'references'}</summary>{row.discovery_sources.map(source => <a className="intelligence-link" key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a>)}</details>}
      <a className="intelligence-link" href={row.url} target="_blank" rel="noopener noreferrer">Official employer careers ↗</a></article>)}</div>
    {data && !employers.length && <p className="methodology">No employers match these directory filters. Try a different category or evidence filter.</p>}
  </section>
}
