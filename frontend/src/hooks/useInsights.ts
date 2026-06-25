import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { PortfolioReview } from '../api/types'

// The AI portfolio review is PROMPT-ONLY: the app never calls an AI model. The
// user runs the assembled prompt (see ExternalGenerate + getReviewPrompt) in
// their own Claude/ChatGPT and pastes the JSON back, which is stored in
// localStorage and surfaced here. Nothing is fetched from the network.

/** Today's date as YYYY-MM-DD (local), used to scope the once-a-day cache. */
function today(): string {
  return new Date().toISOString().slice(0, 10)
}

// Bump the version suffix whenever the review shape changes so stale caches
// from an older format are ignored.
const REVIEW_CACHE_VERSION = 'v3'

function reviewCacheKey(day: string, accountId: string | undefined, target: number): string {
  return `pf-review:${REVIEW_CACHE_VERSION}:${day}:${accountId ?? 'all'}:${target}`
}

function readCachedReview(key: string): PortfolioReview | undefined {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as PortfolioReview) : undefined
  } catch {
    return undefined
  }
}

function writeCachedReview(key: string, data: PortfolioReview): void {
  try {
    localStorage.setItem(key, JSON.stringify(data))
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function lsRemove(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

/**
 * Today's portfolio review, read from localStorage only (no network). It is
 * populated by pasting the model's JSON back via {@link useApplyManualReview};
 * `data` is the stored review or `null` if none has been applied today.
 */
export function useStoredReview(accountId: string | undefined, target: number) {
  const day = today()
  const key = reviewCacheKey(day, accountId, target)
  return useQuery<PortfolioReview | null>({
    queryKey: ['portfolio-review', day, accountId ?? 'all', target],
    queryFn: () => readCachedReview(key) ?? null,
    initialData: () => readCachedReview(key),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: false,
  })
}

/** Clear today's cached review (so the user can paste a fresh one). */
export function clearReviewCache(accountId: string | undefined, target: number): void {
  lsRemove(reviewCacheKey(today(), accountId, target))
}

/**
 * Ingest a portfolio review generated in Claude/ChatGPT and pasted back as JSON.
 * Stores it as today's review. Returns a function that takes parsed JSON and
 * yields an error string (or null on success).
 */
export function useApplyManualReview(accountId: string | undefined, target: number) {
  const qc = useQueryClient()
  const day = today()
  const key = reviewCacheKey(day, accountId, target)

  return (parsed: unknown): string | null => {
    if (!parsed || typeof parsed !== 'object') return 'Expected a JSON object.'
    const o = parsed as Record<string, unknown>
    if (!Array.isArray(o.recommendations)) {
      return 'Expected a JSON object with a "recommendations" array.'
    }
    const data: PortfolioReview = {
      fy: typeof o.fy === 'string' ? o.fy : '',
      target_profit_pct: typeof o.target_profit_pct === 'number' ? o.target_profit_pct : target,
      answer: typeof o.answer === 'string' ? o.answer : '',
      portfolio_commentary:
        typeof o.portfolio_commentary === 'string' ? o.portfolio_commentary : '',
      recommendations: o.recommendations as PortfolioReview['recommendations'],
    }
    writeCachedReview(key, data)
    qc.setQueryData(['portfolio-review', day, accountId ?? 'all', target], data)
    return null
  }
}
