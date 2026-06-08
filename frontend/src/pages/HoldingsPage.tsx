import { useState, useMemo } from 'react'
import { useAccount } from '../context/AccountContext'
import { useStockModal } from '../context/StockModalContext'
import { useHoldings, useExitedHoldings } from '../hooks/usePortfolio'
import { useAccounts, useAddShares } from '../hooks/useAccounts'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import { HoldingStatusBadge } from '../components/ui/StatusBadge'
import { formatINR, formatPct, formatNumber, signClass } from '../utils/format'
import type { Holding } from '../api/types'

function AddSharesForm() {
  const { selectedAccountId } = useAccount()
  const { data: accounts } = useAccounts()
  const addSharesMut = useAddShares()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ symbol: '', exchange: 'NSE', quantity: '', price: '', trade_date: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  // Targets a specific account: the selected one, else the first.
  const accountId = selectedAccountId ?? accounts?.[0]?.id
  const price = Number(form.price) || 0

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setMsg('')
    const qty = Number(form.quantity)
    if (!accountId) { setErr('No account available.'); return }
    if (!form.symbol.trim()) { setErr('Symbol is required.'); return }
    if (!(qty > 0)) { setErr('Quantity must be greater than 0.'); return }
    if (price < 0) { setErr('Price cannot be negative.'); return }
    if (!form.trade_date) { setErr('Date is required.'); return }
    try {
      const res = await addSharesMut.mutateAsync({
        accountId,
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        quantity: qty,
        price,
        trade_date: form.trade_date,
      })
      setMsg(res.message)
      setForm({ symbol: '', exchange: 'NSE', quantity: '', price: '', trade_date: '' })
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to add shares.')
    }
  }

  return (
    <div>
      <button className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
        {open ? 'Close' : '+ Add Shares'}
      </button>
      {open && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title">Add Shares (bonus or missing buy)</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
            Record shares the tradebook doesn't have. Leave <strong>Price 0</strong> for a free
            bonus/split (quantity rises, average dilutes, XIRR unaffected). Enter a <strong>price</strong>
            for a missing buy such as an IPO allotment (adds quantity <em>and</em> cost; counts in XIRR).
          </div>
          <form onSubmit={submit} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
            {accounts && accounts.length > 1 && (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Account</label>
                <select className="form-select" value={accountId ?? ''} disabled
                  onChange={() => { /* account follows the global selector */ }}>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.label}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Symbol</label>
              <input className="form-input" style={{ width: 120 }} placeholder="NSDL"
                value={form.symbol} onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Exchange</label>
              <select className="form-select" value={form.exchange}
                onChange={(e) => setForm((f) => ({ ...f, exchange: e.target.value }))}>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Qty</label>
              <input className="form-input" type="number" min="0" step="any" style={{ width: 90 }} placeholder="18"
                value={form.quantity} onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Price ₹ (0 = bonus)</label>
              <input className="form-input" type="number" min="0" step="any" style={{ width: 110 }} placeholder="0"
                value={form.price} onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Date</label>
              <input className="form-input" type="date"
                value={form.trade_date} onChange={(e) => setForm((f) => ({ ...f, trade_date: e.target.value }))} />
            </div>
            <button className="btn btn-primary btn-sm" type="submit" disabled={addSharesMut.isPending}>
              {addSharesMut.isPending ? 'Adding…' : (price > 0 ? 'Add Buy' : 'Add Bonus')}
            </button>
          </form>
          {err && <div className="error-state" style={{ marginTop: 10 }}>{err}</div>}
          {msg && <div style={{ marginTop: 10, fontSize: 13, color: 'var(--positive)' }}>{msg}</div>}
        </div>
      )}
    </div>
  )
}

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

function ExitedTable({ accountId }: { accountId?: string }) {
  const { openStock } = useStockModal()
  const { data, isLoading, isError, error } = useExitedHoldings(accountId)

  if (isLoading) return <LoadingState message="Loading exited positions…" />
  if (isError) return <ErrorState error={error} context="Exited positions" />
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon="✓"
        title="No exited positions"
        description="Positions you've fully sold out of will appear here, with the average price you held them at."
      />
    )
  }

  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Exchange</th>
              <th style={{ textAlign: 'right' }}>Qty Held</th>
              <th style={{ textAlign: 'right' }}>Avg Price Held</th>
              <th style={{ textAlign: 'right' }}>Exited On</th>
              <th style={{ textAlign: 'right' }}>Realized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={`${p.symbol}-${p.exchange}-${p.exit_date}`}>
                <td>
                  <button
                    type="button"
                    className="link-button"
                    style={{ fontWeight: 700 }}
                    onClick={() => openStock(p.symbol, p.exchange)}
                  >
                    {p.symbol}
                  </button>
                </td>
                <td>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.exchange}</span>
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {formatNumber(p.quantity, 0)}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {formatINR(p.average_price)}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {p.exit_date ?? '—'}
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={signClass(p.realized_pnl)}>
                  {formatINR(p.realized_pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CurrentHoldings() {
  const { openStock } = useStockModal()
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

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''

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

  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <AddSharesForm />
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
                    <button
                      type="button"
                      className="link-button"
                      style={{ fontWeight: 700 }}
                      onClick={() => openStock(h.symbol, h.exchange)}
                    >
                      {h.symbol}
                    </button>
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
    </>
  )
}

export default function HoldingsPage() {
  const { selectedAccountId } = useAccount()
  const [view, setView] = useState<'current' | 'exited'>('current')

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1>Holdings</h1>
        <div className="segmented">
          <button
            type="button"
            className={`segmented-btn${view === 'current' ? ' active' : ''}`}
            onClick={() => setView('current')}
          >
            Current
          </button>
          <button
            type="button"
            className={`segmented-btn${view === 'exited' ? ' active' : ''}`}
            onClick={() => setView('exited')}
          >
            Exited
          </button>
        </div>
      </div>

      {view === 'current' ? <CurrentHoldings /> : <ExitedTable accountId={selectedAccountId} />}
    </div>
  )
}
