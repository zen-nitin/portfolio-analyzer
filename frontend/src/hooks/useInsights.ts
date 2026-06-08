import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRecommendation,
  getAnalysis,
  getAIProviders,
  getPortfolioReview,
  submitPortfolioReviewBatch,
  getBatchJob,
} from '../api/endpoints'
import type { PortfolioReview, ReviewMessage } from '../api/types'

export function useAIProviders() {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: getAIProviders,
  })
}

/** Today's date as YYYY-MM-DD (local), used to scope the once-a-day cache. */
function today(): string {
  return new Date().toISOString().slice(0, 10)
}

// Bump the version suffix whenever the review shape changes so stale caches
// from an older format (e.g. the pre-"actionable-only" verbose list) are ignored.
const REVIEW_CACHE_VERSION = 'v2'

function reviewCacheKey(day: string, accountId: string | undefined, target: number): string {
  return `pf-review:${REVIEW_CACHE_VERSION}:${day}:${accountId ?? 'all'}:${target}`
}

// The in-flight batch id is cached separately from the result so that, while a
// batch runs (it can take minutes), reloading the page RESUMES polling the same
// job instead of resubmitting (which would re-bill the LLM).
function reviewBatchKey(day: string, accountId: string | undefined, target: number): string {
  return `pf-review-batch:${REVIEW_CACHE_VERSION}:${day}:${accountId ?? 'all'}:${target}`
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

function lsGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
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
 * Clear a day's cached review result AND any in-flight batch id, so the next
 * fetch resubmits a fresh batch. Backs the dashboard "Refresh" button.
 */
export function clearReviewCache(accountId: string | undefined, target: number): void {
  const day = today()
  lsRemove(reviewCacheKey(day, accountId, target))
  lsRemove(reviewBatchKey(day, accountId, target))
}

/**
 * AI review of all holdings + watchlist against an FY profit goal.
 *
 * Runs at most once per calendar day per (account, target) and goes through the
 * provider Batch API (~50% cheaper, asynchronous): the query submits a batch,
 * persists the batch id, and polls every 20s until the job completes. The result
 * is persisted to localStorage and seeded back as `initialData`, so reopening
 * the dashboard the same day does NOT re-bill the LLM; reloading mid-run resumes
 * polling the same batch. When batch mode is disabled server-side the submit
 * returns a completed result inline (one round-trip, like before).
 *
 * `data` is `PortfolioReview` once ready, or `null` while the batch is pending.
 */
export function usePortfolioReview(
  accountId: string | undefined,
  target: number,
  enabled: boolean,
) {
  const day = today()
  const key = reviewCacheKey(day, accountId, target)
  const batchKey = reviewBatchKey(day, accountId, target)

  return useQuery<PortfolioReview | null>({
    queryKey: ['portfolio-review', day, accountId ?? 'all', target],
    queryFn: async () => {
      // Already have today's result? Use it (also covered by initialData).
      const cached = readCachedReview(key)
      if (cached) return cached

      // Resume an in-flight batch, or submit a new one.
      let batchId = lsGet(batchKey)
      if (!batchId) {
        const submitted = await submitPortfolioReviewBatch(accountId, target)
        if (submitted.status === 'completed' && submitted.result) {
          // Sync fallback (batch disabled / unsupported): result returned inline.
          writeCachedReview(key, submitted.result)
          return submitted.result
        }
        batchId = submitted.batch_id != null ? String(submitted.batch_id) : null
        if (batchId) {
          try {
            localStorage.setItem(batchKey, batchId)
          } catch {
            /* ignore */
          }
        }
      }
      if (!batchId) return null

      // Poll once; refetchInterval drives subsequent polls while pending.
      const job = await getBatchJob<PortfolioReview>(batchId, 'portfolio_review', target)
      if (job.status === 'completed' && job.result) {
        writeCachedReview(key, job.result)
        lsRemove(batchKey)
        return job.result
      }
      if (job.status === 'failed' || job.status === 'expired' || job.status === 'cancelled') {
        lsRemove(batchKey)
        throw new Error(job.error || `Suggestion batch ${job.status}.`)
      }
      return null // pending — keep polling
    },
    enabled,
    initialData: () => readCachedReview(key),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
    // Re-poll on every (re)mount so returning to the dashboard resumes an
    // in-flight batch. The queryFn is idempotent — it returns the cached result
    // or resumes the persisted batch id, so this never re-bills.
    refetchOnMount: 'always',
    // While the result is not yet in (data === null), poll every 20s.
    refetchInterval: (query) => (query.state.data == null ? 20000 : false),
  })
}

/**
 * Ask a follow-up question about the portfolio review. Sends the conversation
 * transcript (ending with the new user question); the AI answers and returns a
 * refined recommendation set. On success the result replaces the cached daily
 * review (in both the query cache and localStorage), so the dashboard shows the
 * updated suggestions and they persist for the rest of the day.
 */
export function useAskPortfolioReview(accountId: string | undefined, target: number) {
  const qc = useQueryClient()
  const day = today()
  const key = reviewCacheKey(day, accountId, target)
  return useMutation({
    mutationFn: (messages: ReviewMessage[]) => getPortfolioReview(accountId, target, messages),
    onSuccess: (data) => {
      qc.setQueryData(['portfolio-review', day, accountId ?? 'all', target], data)
      try {
        localStorage.setItem(key, JSON.stringify(data))
      } catch {
        /* ignore quota / private-mode errors */
      }
    },
  })
}

/**
 * Ingest a portfolio review generated externally (ChatGPT/Claude) and pasted
 * back as JSON. Caches it as today's review (cancelling any in-flight batch).
 * Returns a function that takes parsed JSON and yields an error string or null.
 */
export function useApplyManualReview(accountId: string | undefined, target: number) {
  const qc = useQueryClient()
  const day = today()
  const key = reviewCacheKey(day, accountId, target)
  const batchKey = reviewBatchKey(day, accountId, target)

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
    lsRemove(batchKey)
    qc.setQueryData(['portfolio-review', day, accountId ?? 'all', target], data)
    return null
  }
}

export function useRecommendation() {
  return useMutation({
    mutationFn: (symbol: string) => getRecommendation(symbol),
  })
}

export function useAnalysis(symbol: string | null) {
  return useQuery({
    queryKey: ['analysis', symbol],
    queryFn: () => getAnalysis(symbol!),
    enabled: !!symbol,
  })
}
