import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWatchlist,
  addWatchlistItem,
  deleteWatchlistItem,
  setWatchlistEntryZone,
  setWatchlistPlan,
  reorderWatchlist,
} from '../api/endpoints'
import type { WatchlistCreate, WatchlistItem, WatchlistSuggestions } from '../api/types'

// Suggestions are PROMPT-ONLY: the app never calls an AI model. The user runs
// the assembled prompt (ExternalGenerate + getWatchlistPrompt) in their own
// Claude/ChatGPT and pastes the JSON back, which is stored in localStorage and
// surfaced here. Scoped per-day so a new day starts fresh.
function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}
function resultKey(day: string): string {
  return `wl-suggest:v3:${day}:result`
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

/** Set or clear a watchlist item's trade-plan notes (catalyst + exit-when). */
export function useSetPlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      catalyst,
      exit_when,
    }: {
      id: string
      catalyst: string | null
      exit_when: string | null
    }) => setWatchlistPlan(id, catalyst, exit_when),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

/**
 * AI watchlist suggestions — PROMPT-ONLY. Read today's applied suggestions from
 * localStorage (no network). They are populated by running the assembled prompt
 * (ExternalGenerate + getWatchlistPrompt) in Claude/ChatGPT and pasting the JSON
 * back via `applyManual`. `clear()` drops them so a fresh set can be pasted.
 *
 * Returns `{ data, applyManual, clear }` where `data` is
 * `{ suggestions, flagged_holdings }` or null.
 */
export function useWatchlistSuggestions() {
  const day = todayStr()
  const rKey = resultKey(day)
  const qc = useQueryClient()

  const query = useQuery<WatchlistSuggestions | null>({
    queryKey: ['watchlist-suggestions', day],
    queryFn: () => readCachedSuggestions(day) ?? null,
    initialData: () => readCachedSuggestions(day),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: false,
  })

  function clear() {
    lsRemove(rKey)
    qc.setQueryData(['watchlist-suggestions', day], null)
  }

  // Ingest JSON generated in Claude/ChatGPT. Returns an error string or null on
  // success; stores it as today's result.
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
    qc.setQueryData(['watchlist-suggestions', day], data)
    return null
  }

  return { data: query.data ?? null, applyManual, clear }
}
