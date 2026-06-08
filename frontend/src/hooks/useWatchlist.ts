import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWatchlist,
  addWatchlistItem,
  deleteWatchlistItem,
  setWatchlistEntryZone,
  reorderWatchlist,
  submitWatchlistSuggestionsBatch,
  getBatchJob,
} from '../api/endpoints'
import { useAIProviders } from './useInsights'
import type { WatchlistCreate, WatchlistItem, WatchlistSuggestions } from '../api/types'

const POLL_INTERVAL_MS = 15000
const DAILY_SUGGESTION_COUNT = 10

// Suggestions auto-run once per day through the async Batch API (which can take
// minutes). The day's result and any in-flight batch id are persisted to
// localStorage (not component state) so leaving the page and coming back — or
// reloading — RESUMES the poll / shows the result instead of losing it.
function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}
function resultKey(day: string): string {
  return `wl-suggest:v2:${day}:result`
}
function batchKey(day: string): string {
  return `wl-suggest:v2:${day}:batch`
}

function lsGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function lsSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
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

function readCachedSuggestions(day: string): WatchlistSuggestions | undefined {
  try {
    const raw = localStorage.getItem(resultKey(day))
    return raw ? (JSON.parse(raw) as WatchlistSuggestions) : undefined
  } catch {
    return undefined
  }
}

export function useWatchlist() {
  return useQuery({
    queryKey: ['watchlist'],
    queryFn: getWatchlist,
  })
}

export function useAddWatchlistItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WatchlistCreate) => addWatchlistItem(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

export function useDeleteWatchlistItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteWatchlistItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

/**
 * Persist a new manual order of watchlist items. Optimistically reorders the
 * cached list so drag-and-drop feels instant; rolls back on error.
 */
export function useReorderWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => reorderWatchlist(ids),
    onMutate: async (ids: string[]) => {
      await qc.cancelQueries({ queryKey: ['watchlist'] })
      const prev = qc.getQueryData<WatchlistItem[]>(['watchlist'])
      if (prev) {
        // ids may be strings while cached ids are numbers — key by String().
        const byId = new Map(prev.map((i) => [String(i.id), i]))
        const next = ids.map((id) => byId.get(String(id))).filter((i): i is WatchlistItem => !!i)
        qc.setQueryData(['watchlist'], next)
      }
      return { prev }
    },
    onError: (_err, _ids, ctx) => {
      if (ctx?.prev) qc.setQueryData(['watchlist'], ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

/** Set or clear a watchlist item's buy entry zone. */
export function useSetEntryZone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      entry_low,
      entry_high,
    }: {
      id: string
      entry_low: number | null
      entry_high: number | null
    }) => setWatchlistEntryZone(id, entry_low, entry_high),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

/**
 * AI watchlist suggestions — auto-generated ONCE PER DAY (10 ideas) through the
 * provider Batch API (~50% cheaper, async), like the dashboard portfolio review.
 *
 * Resilient: the day's result and any in-flight batch id live in localStorage,
 * and the query auto-submits then polls until the batch completes. Leaving the
 * page and returning (or reloading) resumes polling / shows the cached result;
 * a new day triggers a fresh run. `refresh()` regenerates today's bench.
 *
 * Gated on an AI provider being configured (avoids a 503 on every load).
 * Returns `{ data, isPending, isError, error, refresh }` where `data` is
 * `{ suggestions, flagged_holdings }` or null while generating.
 */
export function useWatchlistSuggestions() {
  const day = todayStr()
  const rKey = resultKey(day)
  const bKey = batchKey(day)
  const qc = useQueryClient()

  const providersQ = useAIProviders()
  const aiConfigured = (providersQ.data ?? []).some((p) => p.active && p.configured)

  const query = useQuery<WatchlistSuggestions | null>({
    queryKey: ['watchlist-suggestions', day],
    queryFn: async () => {
      // Today's result already cached?
      const cached = readCachedSuggestions(day)
      if (cached) return cached

      // Resume an in-flight batch, or submit a new one for today.
      let batchId = lsGet(bKey)
      if (!batchId) {
        const submitted = await submitWatchlistSuggestionsBatch(DAILY_SUGGESTION_COUNT)
        if (submitted.status === 'completed' && submitted.result) {
          // Sync fallback (batch disabled / unsupported): result returned inline.
          lsSet(rKey, JSON.stringify(submitted.result))
          return submitted.result
        }
        batchId = submitted.batch_id != null ? String(submitted.batch_id) : null
        if (batchId) lsSet(bKey, batchId)
      }
      if (!batchId) return null

      const job = await getBatchJob<WatchlistSuggestions>(batchId, 'watchlist_suggestions')
      if (job.status === 'completed' && job.result) {
        lsSet(rKey, JSON.stringify(job.result))
        lsRemove(bKey)
        return job.result
      }
      if (job.status === 'failed' || job.status === 'expired' || job.status === 'cancelled') {
        lsRemove(bKey)
        throw new Error(job.error || `Suggestion batch ${job.status}.`)
      }
      return null // pending — keep polling
    },
    enabled: aiConfigured,
    initialData: () => readCachedSuggestions(day),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
    // Re-poll on (re)mount so returning resumes an in-flight batch immediately.
    refetchOnMount: 'always',
    // Keep polling while a batch is in-flight (the batch id is the source of
    // truth — survives unmount and reload).
    refetchInterval: () => (lsGet(bKey) ? POLL_INTERVAL_MS : false),
  })

  function refresh() {
    lsRemove(rKey)
    lsRemove(bKey)
    query.refetch()
  }

  // Ingest JSON generated externally (ChatGPT/Claude). Returns an error string
  // or null on success; caches it as today's result (cancelling any batch).
  function applyManual(parsed: unknown): string | null {
    let data: WatchlistSuggestions
    if (Array.isArray(parsed)) {
      data = { suggestions: parsed, flagged_holdings: [] }
    } else if (
      parsed && typeof parsed === 'object' &&
      Array.isArray((parsed as WatchlistSuggestions).suggestions)
    ) {
      const o = parsed as WatchlistSuggestions
      data = { suggestions: o.suggestions, flagged_holdings: o.flagged_holdings ?? [] }
    } else {
      return 'Expected a JSON object with a "suggestions" array.'
    }
    lsSet(rKey, JSON.stringify(data))
    lsRemove(bKey)
    qc.setQueryData(['watchlist-suggestions', day], data)
    return null
  }

  // The batch id in localStorage is the single source of truth for "in-flight".
  const batchInFlight = !!lsGet(bKey)
  // Suppress transient poll errors while a batch is in-flight (next interval
  // retries); a terminal failure clears the batch id first, so it surfaces here.
  const queryFailed = query.isError && !batchInFlight
  return {
    // Hide any stale result while a fresh batch is running.
    data: batchInFlight ? null : (query.data ?? null),
    isPending: aiConfigured && (batchInFlight || (query.isFetching && !query.data)),
    isError: queryFailed,
    error: (queryFailed ? query.error : null) as unknown,
    refresh,
    applyManual,
  }
}
