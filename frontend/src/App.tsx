import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowRight, ArrowUpRight, Bookmark, BookOpen, BriefcaseBusiness, ChevronDown, Clock3, Compass, ExternalLink, FileText, Filter, GitBranch, Layers3, Menu, Newspaper, Orbit, Radar, Search, Send, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api, type AskResult, type Company, type CompanyPulse, type ContextResult, type Knowledge, type Opportunity, type Overview, type SearchResult, type Signal, type UseCase } from './api'

type Page = 'Overview' | 'Signals' | 'Models' | 'Jobs' | 'Knowledge' | 'Companies' | 'Use cases' | 'Opportunity map' | 'Ask AItlas' | 'Saved' | 'Search'
const nav: { name: Page; icon: typeof Compass }[] = [
  { name: 'Overview', icon: Compass }, { name: 'Signals', icon: Radar }, { name: 'Models', icon: Sparkles }, { name: 'Jobs', icon: BriefcaseBusiness }, { name: 'Knowledge', icon: BookOpen },
  { name: 'Companies', icon: BriefcaseBusiness }, { name: 'Use cases', icon: Layers3 },
  { name: 'Opportunity map', icon: Orbit }, { name: 'Ask AItlas', icon: Sparkles }, { name: 'Saved', icon: Bookmark },
]

function dateLabel(value: string | null) {
  if (!value) return 'Not synced yet'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date)
}
function dayLabel() { return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(new Date()) }
function kindLabel(kind: string) { return kind === 'repo' ? 'Repository' : kind === 'paper' ? 'Research paper' : kind === 'model' ? 'Model' : kind === 'job' ? 'Job' : 'News' }
function sourceLink(url: string, label = 'View source') { return <a className="source-link" href={url} target="_blank" rel="noopener noreferrer">{label}<ArrowUpRight size={14} /></a> }

function Empty({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return <div className="empty"><div className="empty-icon"><Search size={22} /></div><h3>{title}</h3><p>{text}</p>{action}</div>
}

function SignalCard({ item, saved, onSave, onContext, compact = false }: { item: Signal; saved: boolean; onSave: (item: Signal) => void; onContext: (item: Signal) => void; compact?: boolean }) {
  return <article className={`signal-card ${compact ? 'compact' : ''}`}>
    <div className="signal-top"><span className={`kind-pill kind-${item.kind}`}>{item.kind === 'paper' ? <FileText size={12} /> : item.kind === 'repo' ? <GitBranch size={12} /> : item.kind === 'model' ? <Sparkles size={12} /> : <Newspaper size={12} />}{kindLabel(item.kind)}</span><span className="muted small"><Clock3 size={13} /> {dateLabel(item.published_at)}</span></div>
    <h3><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ArrowUpRight size={16} /></a></h3>
    <p className="clamp">{item.summary}</p>
    {(item.kind === 'repo' || item.kind === 'model' || ['business', 'developer', 'both'].includes(item.details?.audience || '')) && <div className="signal-facts">{item.details?.audience && <span>{item.details.audience === 'both' ? 'Business + developer' : item.details.audience}</span>}{item.kind === 'repo' && typeof item.details?.stars === 'number' && <span>{item.details.stars.toLocaleString()} stars</span>}{item.kind === 'repo' && typeof item.details?.stars_delta_since_last_sync === 'number' && item.details.stars_delta_since_last_sync > 0 && <span>+{item.details.stars_delta_since_last_sync} since last sync</span>}{item.kind === 'model' && item.details?.trending_rank && <span>Trending #{item.details.trending_rank}</span>}{item.details?.license && <span>License: {item.details.license}</span>}</div>}
    <div className="signal-bottom"><span className="muted small">{item.source}</span><div className="card-actions"><button title={saved ? 'Remove from saved' : 'Save item'} onClick={() => onSave(item)} className={saved ? 'icon-action active' : 'icon-action'}><Bookmark size={16} fill={saved ? 'currentColor' : 'none'} /></button><button className="text-action" onClick={() => onContext(item)}>Historical context <ArrowRight size={14} /></button></div></div>
  </article>
}

function JobCard({ item }: { item: Signal }) {
  return <article className="job-card"><div className="job-meta"><span className="category-tag">{item.details?.role || 'AI role'}</span><span>{dateLabel(item.published_at)}</span></div><h3>{item.title}</h3><div className="job-company">{item.details?.company || item.source} <span>·</span> {item.details?.location || 'Location not specified'}</div><p className="clamp">{item.summary}</p><div className="job-bottom"><small>Source: {item.source}. Verify availability on the employer board.</small>{sourceLink(item.url, 'View role')}</div></article>
}

function SectionHead({ eyebrow, title, aside }: { eyebrow: string; title: string; aside?: React.ReactNode }) { return <div className="section-head"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{aside}</div> }

export default function App() {
  const [page, setPage] = useState<Page>('Overview')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [signalTotal, setSignalTotal] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [signalAudience, setSignalAudience] = useState('all')
  const [models, setModels] = useState<Signal[]>([])
  const [jobs, setJobs] = useState<Signal[]>([])
  const [jobTotal, setJobTotal] = useState(0)
  const [jobRole, setJobRole] = useState('all')
  const [jobSearchDraft, setJobSearchDraft] = useState('')
  const [jobQuery, setJobQuery] = useState('')
  const [loadingMoreJobs, setLoadingMoreJobs] = useState(false)
  const [knowledge, setKnowledge] = useState<Knowledge[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [companyPulse, setCompanyPulse] = useState<CompanyPulse[]>([])
  const [cases, setCases] = useState<UseCase[]>([])
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [signalKind, setSignalKind] = useState('all')
  const [knowledgeKind, setKnowledgeKind] = useState('all')
  const [industry, setIndustry] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [submittedSearch, setSubmittedSearch] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searchTotal, setSearchTotal] = useState(0)
  const [loadingMoreSearch, setLoadingMoreSearch] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [context, setContext] = useState<ContextResult | null>(null)
  const [contextLoading, setContextLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResult | null>(null)
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState('')
  const [saved, setSaved] = useState<Signal[]>(() => { try { return JSON.parse(localStorage.getItem('aitlas:saved') || '[]') } catch { return [] } })

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const signalPath = `/items?kind=${signalKind === 'all' ? 'signals' : signalKind}&audience=${signalAudience}&limit=100`
      const jobPath = `/items?kind=job&role=${encodeURIComponent(jobRole)}&q=${encodeURIComponent(jobQuery)}&limit=100`
      const [o, s, k, c, u, p, j, m, cp] = await Promise.allSettled([
        api<Overview>('/overview'), api<{ total: number; items: Signal[] }>(signalPath), api<Knowledge[]>('/knowledge'),
        api<Company[]>('/companies'), api<UseCase[]>('/use-cases'), api<Opportunity[]>('/opportunities'),
        api<{ total: number; items: Signal[] }>(jobPath), api<{ total: number; items: Signal[] }>('/items?kind=model&sort=trending&limit=100'), api<CompanyPulse[]>('/company-pulse'),
      ])
      if (o.status === 'fulfilled') setOverview(o.value)
      if (s.status === 'fulfilled') {
        setSignalTotal(s.value.total)
        setSignals(previous => {
          const seen = new Set<string>()
          return [...s.value.items, ...previous].filter(item => !seen.has(item.id) && Boolean(seen.add(item.id))).slice(0, 500)
        })
      }
      if (k.status === 'fulfilled') setKnowledge(k.value)
      if (c.status === 'fulfilled') setCompanies(c.value)
      if (u.status === 'fulfilled') setCases(u.value)
      if (p.status === 'fulfilled') setOpportunities(p.value)
      if (j.status === 'fulfilled') {
        setJobTotal(j.value.total)
        setJobs(previous => {
          const seen = new Set<string>()
          return [...j.value.items, ...previous].filter(item => !seen.has(item.id) && Boolean(seen.add(item.id))).slice(0, 500)
        })
      }
      if (m.status === 'fulfilled') setModels(m.value.items)
      if (cp.status === 'fulfilled') setCompanyPulse(cp.value)
      if ([o, s, k, c, u, p, j, m, cp].some(result => result.status === 'rejected')) setError('Some sections could not be refreshed. Existing data is still available')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not reach the API') }
    finally { setLoading(false) }
  }, [signalKind, signalAudience, jobRole, jobQuery])
  async function loadMoreSignals() {
    setLoadingMore(true)
    try {
      const result = await api<{ total: number; items: Signal[] }>(`/items?kind=${signalKind === 'all' ? 'signals' : signalKind}&audience=${signalAudience}&limit=100&offset=${signals.length}`)
      setSignalTotal(result.total)
      setSignals(previous => {
        const seen = new Set(previous.map(item => item.id))
        return [...previous, ...result.items.filter(item => !seen.has(item.id) && Boolean(seen.add(item.id)))]
      })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load more signals') }
    finally { setLoadingMore(false) }
  }
  async function loadMoreJobs() {
    setLoadingMoreJobs(true)
    try {
      const result = await api<{ total: number; items: Signal[] }>(`/items?kind=job&role=${encodeURIComponent(jobRole)}&q=${encodeURIComponent(jobQuery)}&limit=100&offset=${jobs.length}`)
      setJobTotal(result.total)
      setJobs(previous => {
        const seen = new Set(previous.map(item => item.id))
        return [...previous, ...result.items.filter(item => !seen.has(item.id) && Boolean(seen.add(item.id)))]
      })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load more jobs') }
    finally { setLoadingMoreJobs(false) }
  }
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const timer = window.setInterval(() => { if (!document.hidden) void load() }, 60_000)
    const onVisible = () => { if (!document.hidden) void load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [load])
  useEffect(() => { localStorage.setItem('aitlas:saved', JSON.stringify(saved)) }, [saved])

  function navigate(next: Page) { setPage(next); setMobileOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  function toggleSaved(item: Signal) { setSaved(prev => prev.some(x => x.id === item.id) ? prev.filter(x => x.id !== item.id) : [item, ...prev]) }
  async function openContext(item: Signal) { setContextLoading(true); setContext({ item: { title: item.title, url: item.url }, history: [], explanation: '' }); try { setContext(await api<ContextResult>(`/context/${item.id}`)) } catch { setContext({ item: { title: item.title, url: item.url }, history: [], explanation: 'Historical context is unavailable right now.' }) } finally { setContextLoading(false) } }
  async function runSearch(event: React.FormEvent) { event.preventDefault(); if (searchText.trim().length < 2) return; const query = searchText.trim(); setSubmittedSearch(query); setSearchError(''); navigate('Search'); try { const result = await api<{ total: number; results: SearchResult[] }>(`/search?q=${encodeURIComponent(query)}&limit=30`); setSearchResults(result.results); setSearchTotal(result.total) } catch (err) { setSearchError(err instanceof Error ? err.message : 'Search failed') } }
  async function loadMoreSearch() { if (!submittedSearch) return; setLoadingMoreSearch(true); try { const result = await api<{ total: number; results: SearchResult[] }>(`/search?q=${encodeURIComponent(submittedSearch)}&limit=30&offset=${searchResults.length}`); setSearchResults(previous => [...previous, ...result.results]); setSearchTotal(result.total) } catch (err) { setSearchError(err instanceof Error ? err.message : 'Could not load more results') } finally { setLoadingMoreSearch(false) } }
  async function runAsk(event: React.FormEvent) { event.preventDefault(); if (question.trim().length < 5) return; setAsking(true); setAskError(''); setAnswer(null); try { setAnswer(await api<AskResult>('/ask', { method: 'POST', body: JSON.stringify({ question: question.trim() }) })) } catch (err) { setAskError(err instanceof Error ? err.message : 'Could not answer') } finally { setAsking(false) } }

  const industries = useMemo(() => [...new Set([...cases.map(x => x.industry), ...opportunities.map(x => x.industry)])].sort(), [cases, opportunities])
  const filteredSignals = signals
  const filteredKnowledge = knowledge.filter(item => knowledgeKind === 'all' || item.category === knowledgeKind)
  const filteredCases = cases.filter(item => industry === 'all' || item.industry === industry)
  const filteredOpportunities = opportunities.filter(item => industry === 'all' || item.industry === industry)
  const activeNav = page === 'Search' ? '' : page
  function changeSignalKind(value: string) { setSignals([]); setSignalTotal(0); setSignalKind(value) }
  function changeSignalAudience(value: string) { setSignals([]); setSignalTotal(0); setSignalAudience(value) }
  function changeJobRole(value: string) { setJobs([]); setJobTotal(0); setJobRole(value) }
  function submitJobSearch(event: React.FormEvent) { event.preventDefault(); setJobs([]); setJobTotal(0); setJobQuery(jobSearchDraft.trim()) }
  function viewCompanyJobs(name: string) { setJobRole('all'); setJobSearchDraft(name); setJobs([]); setJobTotal(0); setJobQuery(name); navigate('Jobs') }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand" onClick={() => navigate('Overview')} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') navigate('Overview') }}><span className="brand-icon"><Orbit size={21} strokeWidth={1.8} /></span><span>AItlas<span className="brand-dot">.</span><small>THE LIVING ATLAS OF AI</small></span></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">{nav.slice(0, 8).map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${activeNav === name ? 'selected' : ''}`} onClick={() => navigate(name)}><Icon size={18} strokeWidth={1.8} /><span>{name}</span>{name === 'Signals' && overview && <em>{overview.counts.news + overview.counts.paper + overview.counts.repo + (overview.counts.model || 0)}</em>}{name === 'Jobs' && overview && <em>{overview.counts.job || 0}</em>}</button>)}</nav>
      <div className="nav-caption secondary-caption">PERSONAL</div>
      <nav aria-label="Personal navigation">{nav.slice(8).map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${activeNav === name ? 'selected' : ''}`} onClick={() => navigate(name)}><Icon size={18} strokeWidth={1.8} /><span>{name}</span>{name === 'Saved' && saved.length > 0 && <em>{saved.length}</em>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="source-status"><span className={overview?.refresh_status === 'success' ? 'status-dot live' : overview?.last_refresh ? 'status-dot warning' : 'status-dot'} /><div><strong>{overview?.refresh_status === 'success' ? 'Sources connected' : overview?.last_refresh ? 'Some sources need attention' : 'Awaiting first sync'}</strong><small>{overview?.last_refresh ? `Updated ${dateLabel(overview.last_refresh)}` : 'Run the ingestion worker'}</small></div></div><div className="sidebar-note">Open source intelligence,<br />grounded in sources.</div></div>
    </aside>
    {mobileOpen && <button className="mobile-scrim" aria-label="Close menu" onClick={() => setMobileOpen(false)} />}
    <main className="main">
      <header className="topbar"><button className="menu-button" aria-label="Open menu" onClick={() => setMobileOpen(true)}><Menu size={22} /></button><div className="breadcrumb">AItlas <span>/</span> <strong>{page}</strong></div><form className="global-search" onSubmit={runSearch}><Search size={18} /><input aria-label="Search AItlas" placeholder="Search the atlas..." value={searchText} onChange={e => setSearchText(e.target.value)} /><kbd>↵</kbd></form><div className="topbar-right"><span className="today-date">{dayLabel()}</span><span className="avatar">AI</span></div></header>
      <div className="page-content">
        {error && <div className="error-banner"><span>{error}</span><button onClick={() => void load()}>Retry</button></div>}
        {loading && !overview ? <div className="loading-screen"><span className="loading-orbit"><Orbit size={34} /></span><p>Mapping the AI landscape...</p></div> : <>
          {page === 'Overview' && <>
            <div className="hero"><div className="hero-copy"><div className="hero-eyebrow"><span className="pulse-dot" /> YOUR INTELLIGENCE BRIEFING</div><h1>See the signal.<br /><span>Connect the dots.</span></h1><p>AI moves fast. Track business shifts, developer tools, models, and open roles alongside the ideas and companies behind them.</p><div className="hero-actions"><button className="primary-button" onClick={() => navigate('Signals')}>Explore today’s signals <ArrowRight size={17} /></button><button className="ghost-button" onClick={() => navigate('Ask AItlas')}>Ask the atlas <Sparkles size={16} /></button></div></div><div className="hero-visual" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orbit-center"><Orbit size={36} /></div><span className="orbit-point point-one" /><span className="orbit-point point-two" /><span className="orbit-point point-three" /><span className="orbit-point point-four" /><span className="orbit-label label-one">NOW</span><span className="orbit-label label-two">THEN</span><span className="orbit-label label-three">NEXT</span></div></div>
            <div className="stats-row"><div className="stat-card"><span className="stat-icon violet"><Radar size={20} /></span><div><strong>{(overview?.counts.news || 0) + (overview?.counts.paper || 0) + (overview?.counts.repo || 0) + (overview?.counts.model || 0)}</strong><span>Live signals indexed</span></div><ArrowUpRight size={16} className="stat-arrow" /></div><div className="stat-card"><span className="stat-icon blue"><BookOpen size={20} /></span><div><strong>{overview?.knowledge_count || 0}</strong><span>Historical milestones</span></div><ArrowUpRight size={16} className="stat-arrow" /></div><div className="stat-card"><span className="stat-icon orange"><Layers3 size={20} /></span><div><strong>{overview?.case_count || 0}</strong><span>Evidence-backed use cases</span></div><ArrowUpRight size={16} className="stat-arrow" /></div><div className="stat-card"><span className="stat-icon green"><BriefcaseBusiness size={20} /></span><div><strong>{overview?.counts.job || 0}</strong><span>Open AI jobs</span></div><ArrowUpRight size={16} className="stat-arrow" /></div></div>
            {overview && <div className="brief-strip"><div className="brief-mark"><Sparkles size={20} /></div><div className="brief-copy"><span className="eyebrow">LIVE BRIEF / AUTO-GENERATED FROM SOURCES</span><strong>{overview.brief.count} indexed updates across {overview.brief.source_count} sources in the {overview.brief.window}</strong><span>Most indexed themes: {overview.brief.themes.length ? overview.brief.themes.map(t => `${t.name} (${t.count})`).join(' · ') : 'awaiting source data'}.</span></div><button onClick={() => navigate('Signals')}>Read signals <ArrowRight size={15} /></button></div>}
            <div className="two-column"><section><SectionHead eyebrow="01 / THE PULSE" title="Today’s signal" aside={<button className="section-link" onClick={() => navigate('Signals')}>View all <ArrowRight size={15} /></button>} />{overview?.featured.length ? <div className="card-stack">{overview.featured.slice(0, 3).map(item => <SignalCard key={item.id} item={item} saved={saved.some(x => x.id === item.id)} onSave={toggleSaved} onContext={openContext} compact />)}</div> : <Empty title="Live signals are on their way" text="The source worker has not completed a sync. The atlas below is ready to explore now." />}</section><section><SectionHead eyebrow="02 / EXPLORE" title="The atlas, in layers" /><div className="pathways"><button onClick={() => navigate('Knowledge')}><span className="path-icon history"><BookOpen size={20} /></span><span><strong>Trace the history</strong><small>Follow the ideas that shaped AI</small></span><ArrowUpRight size={17} /></button><button onClick={() => navigate('Companies')}><span className="path-icon companies"><BriefcaseBusiness size={20} /></span><span><strong>See AI in practice</strong><small>Evidence from companies and teams</small></span><ArrowUpRight size={17} /></button><button onClick={() => navigate('Use cases')}><span className="path-icon uses"><Layers3 size={20} /></span><span><strong>Find a use case</strong><small>Real deployments, source by source</small></span><ArrowUpRight size={17} /></button><button onClick={() => navigate('Opportunity map')}><span className="path-icon gaps"><Compass size={20} /></span><span><strong>Spot an opening</strong><small>Curated hypotheses worth testing</small></span><ArrowUpRight size={17} /></button></div><div className="freshness-note"><ShieldCheck size={19} /><p><strong>Evidence first.</strong> Every profile, milestone, and opportunity points to a source. Opportunity ideas are labeled as hypotheses.</p></div></section></div>
            <section className="history-preview"><SectionHead eyebrow="03 / DEEP MEMORY" title="Ideas have a lineage" aside={<button className="section-link" onClick={() => navigate('Knowledge')}>Explore timeline <ArrowRight size={15} /></button>} /><div className="mini-timeline">{knowledge.slice(-5).map(x => <a key={x.id} href={x.source_url} target="_blank" rel="noopener noreferrer"><span>{x.year}</span><i /><strong>{x.title}</strong></a>)}</div></section>
          </>}
          {page === 'Signals' && <>
            <div className="page-heading"><div><span className="eyebrow">NOW / LIVE INTELLIGENCE</span><h1>The signal feed<span className="accent-dot">.</span></h1><p>Business shifts and developer developments from public publishers, papers, repositories, and model listings. Sources poll on their own schedules.</p></div><div className="heading-side"><span className="small muted">Last sync</span><strong>{dateLabel(overview?.last_refresh || null)}</strong><button className="section-link" onClick={() => void load()}>Refresh view <ArrowRight size={14} /></button></div></div>
            <div className="filters"><div className="segmented">{[['all', 'All signals'], ['news', 'News'], ['paper', 'Papers'], ['repo', 'Repos'], ['model', 'Models']].map(([value, label]) => <button key={value} className={signalKind === value ? 'active' : ''} onClick={() => changeSignalKind(value)}>{label}</button>)}</div><span className="filter-count"><Filter size={15} /> {filteredSignals.length} of {signalTotal}</span></div>
            <div className="filters audience-filters"><span className="muted small">Audience</span><div className="segmented">{[['all', 'Everything'], ['business', 'Business'], ['developer', 'Developers']].map(([value, label]) => <button key={value} className={signalAudience === value ? 'active' : ''} onClick={() => changeSignalAudience(value)}>{label}</button>)}</div></div>
            {filteredSignals.length ? <div className="signal-grid">{filteredSignals.map(item => <SignalCard key={item.id} item={item} saved={saved.some(x => x.id === item.id)} onSave={toggleSaved} onContext={openContext} />)}</div> : <Empty title="No signals in this view" text="Try another filter or check source health below." />}
            {signals.length < signalTotal && <div className="load-more"><button className="ghost-button" disabled={loadingMore} onClick={() => void loadMoreSignals()}>{loadingMore ? 'Loading...' : `Load more signals (${signals.length} of ${signalTotal})`}</button></div>}
            {overview && <div className="source-panel"><h3>Source health</h3><div className="source-list">{overview.sources.map(source => <div key={source.name}><span className={source.last_error ? 'status-dot warning' : source.last_success_at ? 'status-dot live' : 'status-dot'} /><strong>{source.name}</strong><small>{!source.enabled ? 'Paused' : source.last_error || `${source.interval_minutes} min cadence · last ${dateLabel(source.last_success_at)}`}</small></div>)}</div></div>}
          </>}
          {page === 'Models' && <>
            <div className="page-heading"><div><span className="eyebrow">DEVELOPER RESOURCES</span><h1>Models gaining attention<span className="accent-dot">.</span></h1><p>Current public Hugging Face trending listings with tasks, download counts, and license labels when provided. Inspect each model card and license before use.</p></div><div className="heading-symbol"><Sparkles size={34} /></div></div>
            {models.length ? <div className="signal-grid">{models.map(item => <SignalCard key={item.id} item={item} saved={saved.some(x => x.id === item.id)} onSave={toggleSaved} onContext={openContext} />)}</div> : <Empty title="No models indexed yet" text="The Hugging Face source has not completed its first sync." />}
          </>}
          {page === 'Jobs' && <>
            <div className="page-heading"><div><span className="eyebrow">AI CAREER RADAR</span><h1>Open roles in AI<span className="accent-dot">.</span></h1><p>Live published roles from selected company job boards. Search titles, employers and locations; check the employer listing before applying.</p></div><div className="heading-symbol"><BriefcaseBusiness size={34} /></div></div>
            <div className="job-tools"><form className="job-search" onSubmit={submitJobSearch}><Search size={17} /><input aria-label="Search jobs" placeholder="Role, company or location" value={jobSearchDraft} onChange={event => setJobSearchDraft(event.target.value)} /><button type="submit">Search</button></form><label className="select-wrap"><Filter size={15} /><select aria-label="Filter job role" value={jobRole} onChange={event => changeJobRole(event.target.value)}>{['all', 'Research & AI', 'Engineering', 'Product & design', 'Business & operations'].map(role => <option value={role} key={role}>{role === 'all' ? 'All roles' : role}</option>)}</select><ChevronDown size={15} /></label><span className="filter-count">{jobs.length} of {jobTotal} open roles</span></div>
            {jobs.length ? <div className="job-grid">{jobs.map(item => <JobCard key={item.id} item={item} />)}</div> : <Empty title="No matching open roles" text="Try another role or search term. Boards refresh hourly and close listings after repeated absence." />}
            {jobs.length < jobTotal && <div className="load-more"><button className="ghost-button" disabled={loadingMoreJobs} onClick={() => void loadMoreJobs()}>{loadingMoreJobs ? 'Loading...' : `Load more jobs (${jobs.length} of ${jobTotal})`}</button></div>}
          </>}
          {page === 'Knowledge' && <><div className="page-heading"><div><span className="eyebrow">THEN / DEEP MEMORY</span><h1>History behind the hype<span className="accent-dot">.</span></h1><p>A focused starting map of the ideas behind modern AI. Each milestone links to its original paper.</p></div><div className="heading-symbol"><BookOpen size={34} /></div></div><div className="filters"><div className="segmented">{['all', ...new Set(knowledge.map(x => x.category))].map(value => <button key={value} className={knowledgeKind === value ? 'active' : ''} onClick={() => setKnowledgeKind(value)}>{value === 'all' ? 'All fields' : value}</button>)}</div></div><div className="timeline">{filteredKnowledge.map((row, index) => <article className="timeline-item" key={row.id}><div className="timeline-year"><span>{row.year}</span><i /></div><div className="timeline-card"><div className="timeline-meta"><span className="category-tag">{row.category}</span><span className="muted small">Milestone {String(index + 1).padStart(2, '0')}</span></div><h3>{row.title}</h3><p>{row.summary}</p><div className="tag-row">{row.tags.map(tag => <span key={tag}>{tag}</span>)}</div>{sourceLink(row.source_url, row.source_label)}</div></article>)}</div></>}
          {page === 'Companies' && <>
            <div className="page-heading"><div><span className="eyebrow">COMPANY INTELLIGENCE</span><h1>Who is building what<span className="accent-dot">.</span></h1><p>Follow live hiring and source mentions alongside reviewed, cited company evidence. Hiring and mentions do not establish a company's technology stack.</p></div><div className="heading-symbol"><BriefcaseBusiness size={34} /></div></div>
            <SectionHead eyebrow="LIVE / PUBLIC JOB BOARDS" title="Company hiring pulse" />
            <div className="pulse-grid">{companyPulse.map(company => <article className="pulse-card" key={company.name}><span className="eyebrow">PUBLISHED ROLES</span><h3>{company.name}</h3><strong>{company.open_roles} open roles</strong><small>Board checked {dateLabel(company.last_checked)}</small><button className="section-link" onClick={() => viewCompanyJobs(company.name)}>Explore jobs <ArrowRight size={15} /></button>{company.recent_mentions.length > 0 && <div className="pulse-mentions"><span>Recent news mentions</span>{company.recent_mentions.map(item => <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ArrowUpRight size={13} /></a>)}</div>}</article>)}</div>
            <SectionHead eyebrow="REVIEWED / SOURCE LINKED" title="Evidence profiles" />
            <div className="company-grid">{companies.map(company => <article className="company-card" key={company.id}><div className="company-top"><div className="company-avatar">{company.name.slice(0, 1)}</div><span className="category-tag">{company.industry}</span></div><h2>{company.name}</h2><p>{company.summary}</p><div className="evidence-label"><ShieldCheck size={16} /> {company.evidence.length} cited signal{company.evidence.length === 1 ? '' : 's'}</div><div className="evidence-list">{company.evidence.map(e => <div key={e.id}><strong>{e.title}</strong><p>{e.claim}</p>{sourceLink(e.source_url, e.source_label)}</div>)}</div>{company.recent_mentions.length > 0 && <div className="company-mentions"><strong>Recent source mentions</strong><small>Mentions are news signals, not proof of adoption.</small>{company.recent_mentions.map(item => <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ArrowUpRight size={14} /></a>)}</div>}</article>)}</div>
          </>}
          {page === 'Use cases' && <><div className="page-heading"><div><span className="eyebrow">REAL-WORLD APPLICATIONS</span><h1>Ideas in production<span className="accent-dot">.</span></h1><p>Discover documented deployments, outcomes, and the sources behind them.</p></div><div className="heading-symbol"><Layers3 size={34} /></div></div><div className="filters"><label className="select-wrap"><Filter size={15} /><select value={industry} onChange={e => setIndustry(e.target.value)}><option value="all">All industries</option>{industries.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={15} /></label><span className="filter-count">{filteredCases.length} documented cases</span></div><div className="case-grid">{filteredCases.map(row => <article className="case-card" key={row.id}><div className="case-top"><span className="category-tag">{row.industry}</span><span className="muted small">{row.maturity}</span></div><h2>{row.title}</h2><div className="case-company"><span className="tiny-logo">{(row.company || '?').slice(0, 1)}</span><strong>{row.company}</strong><span>· {row.domain}</span></div><p>{row.summary}</p><div className="outcome"><strong>Reported outcome</strong><p>{row.outcome}</p></div><div className="tag-row">{row.tags.map(tag => <span key={tag}>{tag}</span>)}</div>{sourceLink(row.evidence_url, row.evidence_label)}</article>)}</div></>}
          {page === 'Opportunity map' && <><div className="page-heading"><div><span className="eyebrow">NEXT / OPPORTUNITY LAB</span><h1>Questions worth asking<span className="accent-dot">.</span></h1><p>Exploratory ideas connected to real evidence. These are hypotheses for discovery, not measured market gaps.</p></div><div className="heading-symbol"><Compass size={34} /></div></div><div className="hypothesis-banner"><Sparkles size={20} /><div><strong>Hypothesis board</strong><p>Market size, penetration, and defensibility need independent validation before an investment decision.</p></div></div><div className="filters"><label className="select-wrap"><Filter size={15} /><select value={industry} onChange={e => setIndustry(e.target.value)}><option value="all">All industries</option>{industries.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={15} /></label></div><div className="opportunity-grid">{filteredOpportunities.map((row, index) => <article className="opportunity-card" key={row.id}><div className="opportunity-top"><span className="opportunity-number">0{index + 1}</span><span className="hypothesis-tag">HYPOTHESIS</span></div><div className="opportunity-sector">{row.industry} <ArrowDownRight size={15} /> {row.capability}</div><h2>{row.title}</h2><p>{row.thesis}</p><div className="barrier"><strong>What makes it hard</strong><span>{row.barrier}</span></div>{sourceLink(row.evidence_url, 'Adjacent evidence')}</article>)}</div></>}
          {page === 'Ask AItlas' && <><div className="page-heading"><div><span className="eyebrow">ASK / EVIDENCE-BASED EXPLORATION</span><h1>Ask the atlas<span className="accent-dot">.</span></h1><p>Search across history, live signals, companies, and use cases. Answers include sources.</p></div><div className="heading-symbol"><Sparkles size={34} /></div></div><div className="ask-layout"><div className="ask-panel"><div className="ask-intro"><div className="ask-orb"><Sparkles size={27} /></div><h2>What are you curious about?</h2><p>Try a question about a concept, a company, or how an idea connects to a current development.</p></div><div className="suggestions">{[...knowledge.slice(-2).map(row => `What is ${row.title}?`), ...cases.slice(0, 1).map(row => `How is AI used in ${row.domain.toLowerCase()}?`)].map(q => <button key={q} onClick={() => setQuestion(q)}>{q}<ArrowUpRight size={15} /></button>)}</div><form className="ask-form" onSubmit={runAsk}><input aria-label="Your question" placeholder="Ask a question about AI..." value={question} onChange={e => setQuestion(e.target.value)} /><button disabled={asking || question.trim().length < 5} aria-label="Send question"><Send size={18} /></button></form><div className="ask-disclaimer"><ShieldCheck size={15} /> Local model is optional. Extractive answers work without one.</div></div><div className="answer-panel"><span className="eyebrow">THE RESPONSE</span>{asking ? <div className="answer-placeholder">Searching the atlas...</div> : askError ? <div className="answer-placeholder error-text">{askError}</div> : answer ? <><div className="answer-text">{answer.answer}</div><div className="answer-mode">{answer.mode === 'local_model_review_sources' ? 'Local model synthesis · review sources' : answer.mode === 'extractive' ? 'Extracted from indexed sources' : 'No matching evidence'}</div><h3>Sources used</h3><div className="citation-list">{answer.citations.map(c => <a href={c.url} target="_blank" rel="noopener noreferrer" key={c.number}><span>[{c.number}]</span><strong>{c.title}</strong><ArrowUpRight size={15} /></a>)}</div></> : <div className="answer-placeholder">Your answer and citations will appear here.</div>}</div></div></>}
          {page === 'Saved' && <><div className="page-heading"><div><span className="eyebrow">PERSONAL COLLECTION</span><h1>Your saved signals<span className="accent-dot">.</span></h1><p>Saved in this browser on this device. Export and sync are planned for accounts.</p></div><div className="heading-symbol"><Bookmark size={34} /></div></div>{saved.length ? <div className="signal-grid">{saved.map(item => <SignalCard key={item.id} item={item} saved onSave={toggleSaved} onContext={openContext} />)}</div> : <Empty title="Nothing saved yet" text="Bookmark an item from the signal feed to keep it here." action={<button className="primary-button" onClick={() => navigate('Signals')}>Browse signals <ArrowRight size={16} /></button>} />}</>}
          {page === 'Search' && <><div className="page-heading"><div><span className="eyebrow">ALL / UNIFIED SEARCH</span><h1>Search the atlas<span className="accent-dot">.</span></h1><p>{searchTotal} results for “{submittedSearch}” across live articles, models, jobs, companies, history and use cases.</p></div></div>{searchError ? <div className="error-banner">{searchError}</div> : searchResults.length ? <><div className="search-results">{searchResults.map((row, i) => <a href={row.url} target="_blank" rel="noopener noreferrer" key={`${row.url}-${i}`}><span className="category-tag">{row.type}</span><div><h3>{row.title}</h3><p>{row.snippet}</p></div><ExternalLink size={17} /></a>)}</div>{searchResults.length < searchTotal && <div className="load-more"><button className="ghost-button" disabled={loadingMoreSearch} onClick={() => void loadMoreSearch()}>{loadingMoreSearch ? 'Loading...' : `Load more results (${searchResults.length} of ${searchTotal})`}</button></div>}</> : <Empty title="No matching sources" text="Try a different term such as transformer, support, or model." />}</>}

        </>}
      </div>
      <footer className="footer"><span>© {new Date().getFullYear()} AItlas</span><span>Built for curious minds. Verify claims at their sources.</span><span>Open source · Local first</span></footer>
    </main>
    {context && <div className="modal-backdrop" onClick={() => setContext(null)}><aside className="context-panel" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Historical context"><div className="context-header"><span className="eyebrow">CONNECT THE DOTS</span><button aria-label="Close context" onClick={() => setContext(null)}><X size={20} /></button></div><h2>Historical context</h2><p className="context-subtitle">Related to <strong>{context.item.title}</strong></p>{contextLoading ? <p className="muted">Finding related history...</p> : context.history.length ? <div className="context-history">{context.history.map(row => <div key={row.id}><span>{row.year} · {row.category}</span><h3>{row.title}</h3><p>{row.summary}</p>{sourceLink(row.source_url, 'Read original paper')}</div>)}</div> : <Empty title="No clear match" text="This item has no strong connection to the current historical collection." />}<p className="context-caveat"><ShieldCheck size={16} /> {context.explanation}</p></aside></div>}
  </div>
}
