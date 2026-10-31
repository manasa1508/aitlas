export type Signal = { id: string; kind: 'news' | 'paper' | 'repo' | 'model' | 'job'; title: string; summary: string; url: string; source: string; published_at: string; tags: string[]; details: { audience?: string; last_checked_at?: string; date_basis?: string; source_job_id?: string; workplace_type?: string; employment_type?: string; source_type?: string; category?: string; ai_related?: boolean; points?: number; upvotes?: number; attention_source?: string; github_url?: string | null; project_url?: string | null; trending_checked_at?: string; created_at?: string; pushed_at?: string; similar_coverage?: {title: string; url: string; source: string}[]; company?: string; location?: string; department?: string; role?: string; stars?: number; stars_delta_since_last_sync?: number | null; downloads?: number; likes?: number; trending_rank?: number; license?: string | null; task?: string }; score: number; tier: string }
export type Knowledge = { id: string; title: string; year: number; category: string; summary: string; source_url: string; source_label: string; tags: string[]; related_ids: string[] }
export type Evidence = { id: string; title: string; claim: string; source_url: string; source_label: string; observed_at: string | null }
export type Company = { id: string; name: string; industry: string; summary: string; website: string; evidence: Evidence[]; recent_mentions: Signal[] }
export type CompanyPulse = { name: string; open_roles: number; board_url: string; last_checked: string | null; recent_mentions: Signal[] }
export type UseCase = { id: string; company: string | null; title: string; industry: string; domain: string; summary: string; outcome: string; evidence_url: string; evidence_label: string; maturity: string; tags: string[] }
export type Opportunity = { id: string; title: string; industry: string; capability: string; thesis: string; barrier: string; evidence_url: string; evidence_label: string; status: string }
export type Overview = { counts: Record<string, number>; knowledge_count: number; case_count: number; company_count: number; featured: Signal[]; latest: Signal[]; brief: { window: string; count: number; source_count: number; themes: { name: string; count: number }[] }; last_refresh: string | null; refresh_status: string; sources: { name: string; enabled: boolean; status: string; interval_minutes: number; next_fetch_at: string | null; last_success_at: string | null; last_error: string | null }[] }
export type SearchResult = { type: string; title: string; snippet: string; url: string; date: string | null }
export type AskResult = { answer: string; citations: (SearchResult & { number: number })[]; mode: string }
export type ContextResult = { item: { title: string; url: string }; history: Knowledge[]; explanation: string }

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try { detail = (await response.json()).detail || detail } catch { /* use HTTP status */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export type Employer = {name: string; category: string; sector?: string; url: string; open_roles: number | null; coverage: string; locations: string[]; last_checked: string | null; last_error?: string | null; adapter?: string; recognitions?: {kind: string; label: string; year: number; source_url: string}[]}
export type EmployerResponse = {employers: Employer[]; rating_status: string; coverage_summary: {connected_employers: number; synced_employers: number; failing_employers: number; career_links_only: number; matching_roles: number}}
export type IntelligenceData = {window_days: number; sample_size: number; sample_truncated: boolean; methodology: string; topics: {id: string; name: string; count: number; previous_count: number; source_count: number}[]; discoveries: Signal[]; repos: Signal[]; shifts: {item: Signal; label: string; claim_excerpt: string; status: string}[]; markets: {symbol: string; name: string; news_count: number; reports: Signal[]; reaction_reports: Signal[]; quote_url: string; quote_status: string}[]}
