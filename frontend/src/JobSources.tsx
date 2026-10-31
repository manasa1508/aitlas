import { useEffect, useState } from 'react'
import { api } from './api'

type Searches = {coverage: string; searches: {city: string; location: string; keywords: string; links: {name: string; url: string}[]}[]}

export default function JobSources({ city, role, aiOnly, query }: { city: string; role: string; aiOnly: boolean; query: string }) {
  const [data, setData] = useState<Searches | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setData(null); setError('')
    api<Searches>(`/job-search-links?city=${city}&role=${encodeURIComponent(role)}&ai_only=${aiOnly}&q=${encodeURIComponent(query)}`)
      .then(result => { if (active) setData(result) }).catch(() => { if (active) setError('External search links are temporarily unavailable.') })
    return () => { active = false }
  }, [city, role, aiOnly, query])
  return <details className="source-panel job-discovery"><summary>Broaden your search: LinkedIn, Indeed, Naukri and Foundit</summary><p className="methodology">{data?.coverage || error || 'Preparing city-specific search links…'} These providers may require sign-in. Use their saved searches and alerts for ongoing discovery, and confirm the employer and requisition before applying.</p><div className="company-grid">{data?.searches.map(search => <article className="signal-card" key={search.city}><h3>{search.location}</h3><p>{search.keywords || 'All keywords'} · LinkedIn and Indeed start with the past week</p><div className="external-job-links">{search.links.map(link => <a className="source-link" key={link.name} href={link.url} target="_blank" rel="noopener noreferrer">{link.name} ↗</a>)}</div></article>)}</div><p className="methodology">Connected employer feeds cover a selected registry. Search these providers and use their saved alerts to discover vacancies beyond that registry.</p></details>
}
