import { useState, useMemo } from 'react'
import { useAccount } from '../context/AccountContext'
import { useHoldings } from '../hooks/usePortfolio'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import { HoldingStatusBadge } from '../components/ui/StatusBadge'
import { formatINR, formatPct, formatNumber, signClass } from '../utils/format'
import type { Holding } from '../api/types'

type SortKey = keyof Holding
type SortDir = 'asc' | 'desc'

const COLUMNS: { key: SortKey; label: string; align?: 'right' }[] = [
  { key: 'symbol',        label: 'Symbol' },
  { key: 'exchange',      label: 'Exchange' },
  { key: 'quantity',      label: 'Qty',         align: 'right' },
  { key: 'average_price', label: 'Avg Price',   align: 'right' },
  { key: 'last_price',    label: 'LTP',         align: 'right' },
  { key: 'pnl',           label: 'P&L',         align: 'right' },
  { key: 'pnl_pct',       label: 'P&L %',       align: 'right' },
  { key: 'day_change',    label: 'Day Change',  align: 'right' },
  { key: 'status',        label: 'Status' },
]

function compareHoldings(a: Holding, b: Holding, key: SortKey, dir: SortDir): number {
  const av = a[key]
  const bv = b[key]
  if (av === bv) return 0
  const cmp = av < bv ? -1 : 1
  return dir === 'asc' ? cmp : -cmp
}

export default function HoldingsPage() {
  const { selectedAccountId } = useAccount()
  const { data: holdings, isLoading, isError, error } = useHoldings(selectedAccountId)

  const [sortKey, setSortKey] = useState<SortKey>('pnl')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    if (!holdings) return []
    return [...holdings].sort((a, b) => compareHoldings(a, b, sortKey, sortDir))
  }, [holdings, sortKey, sortDir])

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (isLoading) return <LoadingState message="Loading holdings…" />
  if (isError) return <ErrorState error={error} context="Holdings" />
  if (!sorted.length) {
    return (
      <EmptyState
        icon="◉"
        title="No holdings found"
        description="Sync your Zerodha account or import a tradebook CSV."
      />
    )
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''

  return (
    <div>
      <div className="page-header">
        <h1>{sorted.length} Holdings</h1>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    style={{ textAlign: col.align ?? 'left' }}
                  >
                    {col.label}
                    <span className="sort-arrow">{arrow(col.key)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((h) => (
                <tr key={`${h.symbol}-${h.exchange}`}>
                  <td>
                    <strong>{h.symbol}</strong>
                  </td>
                  <td>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{h.exchange}</span>
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {formatNumber(h.quantity, 0)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {formatINR(h.average_price)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {formatINR(h.last_price)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={signClass(h.pnl)}>
                    {formatINR(h.pnl)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={signClass(h.pnl_pct)}>
                    {formatPct(h.pnl_pct)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={signClass(h.day_change)}>
                    {formatINR(h.day_change)}
                  </td>
                  <td>
                    <HoldingStatusBadge status={h.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
