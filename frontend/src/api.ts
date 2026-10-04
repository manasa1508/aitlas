export type Signal = { id: string; kind: 'news' | 'paper' | 'repo'; title: string; summary: string; url: string; source: string; published_at: string; tags: string[]; score: number; tier: string }
export type Knowledge = { id: string; title: string; year: number; category: string; summary: string; source_url: string; source_label: string; tags: string[]; related_ids: string[] }
export type Evidence = { id: string; title: string; claim: string; source_url: string; source_label: string; observed_at: string | null }
export type Company = { id: string; name: string; industry: string; summary: string; website: string; evidence: Evidence[]; recent_mentions: Signal[] }
export type UseCase = { id: string; company: string | null; title: string; industry: string; domain: string; summary: string; outcome: string; evidence_url: string; evidence_label: string; maturity: string; tags: string[] }
export type Opportunity = { id: string; title: string; industry: string; capability: string; thesis: string; barrier: string; evidence_url: string; evidence_label: string; status: string }
export type Overview = { counts: Record<string, number>; knowledge_count: number; case_count: number; company_count: number; featured: Signal[]; latest: Signal[]; brief: { window: string; count: number; source_count: number; themes: { name: string; count: number }[] }; last_refresh: string | null; refresh_status: string; sources: { name: string; enabled: boolean; interval_minutes: number; next_fetch_at: string | null; last_success_at: string | null; last_error: string | null }[] }
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
