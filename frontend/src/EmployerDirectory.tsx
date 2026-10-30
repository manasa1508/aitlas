import { useEffect, useState } from 'react'
import { api, type Employer } from './api'

export default function EmployerDirectory({ city, aiOnly, onSelect }: { city: string; aiOnly: boolean; onSelect: (name: string) => void }) {
  const [data, setData] = useState<{employers: Employer[]; rating_status: string} | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => {
    let active = true
    async function load() {
      try { const result = await api<{employers: Employer[]; rating_status: string}>(`/employers?city=${city}&ai_only=${aiOnly}`); if (active) { setData(result); setError('') } }
      catch { if (active) setError('Employer coverage could not be refreshed.') }
    }
    void load(); const timer = window.setInterval(() => { if (!document.hidden) void load() }, 60_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [city, aiOnly])
  return <section className="source-panel"><h3>India employer watchlist</h3><p className="methodology">{data?.rating_status} Counts respect your city and AI role filters. “Official careers link” means roles are not indexed here; use the employer’s location filters there.</p><input className="directory-search" aria-label="Search employers" placeholder="Find an employer…" value={query} onChange={e => setQuery(e.target.value)} />{error && <p className="error-text">{error}</p>}<div className="company-grid">{data?.employers.filter(row => row.name.toLowerCase().includes(query.toLowerCase())).map(row => <article className="signal-card" key={row.name}><span className="category-tag">{row.category}</span><h3>{row.name}</h3>{row.coverage === 'public_feed' ? <><p>{row.open_roles} indexed matching roles{row.last_checked ? ` · checked ${new Date(row.last_checked).toLocaleString()}` : ' · awaiting sync'}</p><p>{row.locations.join(' · ')}</p><button className="ghost-button" onClick={() => onSelect(row.name)}>View matching jobs</button></> : <p>Official careers link · live job coverage not connected</p>}<a className="intelligence-link" href={row.url} target="_blank" rel="noopener noreferrer">Official employer careers ↗</a></article>)}</div></section>
}
