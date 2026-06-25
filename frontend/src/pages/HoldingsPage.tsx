import { useState, useMemo } from 'react'
import { useAccount } from '../context/AccountContext'
import { useStockModal } from '../context/StockModalContext'
import { useHoldings, useExitedHoldings } from '../hooks/usePortfolio'
import { useAccounts, useAddShares, useSellShares } from '../hooks/useAccounts'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import { HoldingStatusBadge } from '../components/ui/StatusBadge'
import HoldingDetailModal from '../components/HoldingDetailModal'
import { formatINR, formatPct, formatNumber, signClass } from '../utils/format'
import type { Holding } from '../api/types'

function AddSharesForm({ open }: { open: boolean }) {
  const { selectedAccountId } = useAccount()
  const { data: accounts } = useAccounts()
  const addSharesMut = useAddShares()
  const [form, setForm] = useState({ symbol: '', exchange: 'NSE', trade_type: 'buy', quantity: '', price: '', trade_date: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  // Targets a specific account: the selected one, else the first.
  const accountId = selectedAccountId ?? accounts?.[0]?.id
  const isBonus = form.trade_type === 'bonus'
  // A bonus is free, so its price is forced to 0; a buy uses the entered price.
  const price = isBonus ? 0 : Number(form.price) || 0

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setMsg('')
    const qty = Number(form.quantity)
    if (!accountId) { setErr('No account available.'); return }
    if (!form.symbol.trim()) { setErr('Symbol is required.'); return }
    if (!(qty > 0)) { setErr('Quantity must be greater than 0.'); return }
    if (!isBonus && !(price > 0)) { setErr('Price must be greater than 0 for a buy.'); return }
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
      setForm({ symbol: '', exchange: 'NSE', trade_type: 'buy', quantity: '', price: '', trade_date: '' })
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to add shares.')
    }
  }

  if (!open) return null

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="card-title">Add Shares (bonus or missing buy)</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        Record shares the tradebook doesn't have. Pick <strong>bonus</strong> for free bonus/split
        shares (quantity rises, average dilutes, XIRR unaffected) or <strong>buy</strong> for a missing
        buy such as an IPO allotment (adds quantity <em>and</em> cost; counts in XIRR).
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
          <label className="form-label">Type</label>
          <select className="form-select" value={form.trade_type}
            onChange={(e) => setForm((f) => ({ ...f, trade_type: e.target.value }))}>
            <option value="buy">buy</option>
            <option value="bonus">bonus</option>
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Qty</label>
          <input className="form-input" type="number" min="0" step="any" style={{ width: 90 }} placeholder="18"
            value={form.quantity} onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Price ₹</label>
          <input className="form-input" type="number" min="0" step="any" style={{ width: 110 }} placeholder="0"
            disabled={isBonus}
            value={isBonus ? '0' : form.price}
            onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Date</label>
          <input className="form-input" type="date"
            value={form.trade_date} onChange={(e) => setForm((f) => ({ ...f, trade_date: e.target.value }))} />
        </div>
        <button className="btn btn-primary btn-sm" type="submit" disabled={addSharesMut.isPending}>
          {addSharesMut.isPending ? 'Adding…' : (isBonus ? 'Add Bonus' : 'Add Buy')}
        </button>
      </form>
      {err && <div className="error-state" style={{ marginTop: 10 }}>{err}</div>}
      {msg && <div style={{ marginTop: 10, fontSize: 13, color: 'var(--positive)' }}>{msg}</div>}
    </div>
  )
}

function RecordSaleForm({ open }: { open: boolean }) {
  const { selectedAccountId } = useAccount()
  const { data: accounts } = useAccounts()
  const sellMut = useSellShares()
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({ symbol: '', quantity: '', price: '', trade_date: today })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  // Targets a specific account (the selected one, else the first) and offers
  // exactly that account's current holdings to sell — so you can only sell what
  // you hold, and we have the symbol/exchange/avg-cost without free typing.
  const accountId = selectedAccountId ?? accounts?.[0]?.id
  const { data: holdings } = useHoldings(accountId)

  const selected = holdings?.find((h) => h.symbol === form.symbol)
  const heldQty = selected?.quantity ?? 0
  const qty = Number(form.quantity) || 0
  const price = Number(form.price) || 0
  // Live realized-P&L estimate: shares × (sale price − average cost held).
  const estPnl = selected ? (price - selected.average_price) * qty : 0

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setMsg('')
    if (!accountId) { setErr('No account available.'); return }
    if (!selected) { setErr('Pick a holding to sell.'); return }
    if (!(qty > 0)) { setErr('Quantity must be greater than 0.'); return }
    if (qty > heldQty + 1e-9) { setErr(`You only hold ${formatNumber(heldQty, 0)} ${selected.symbol}.`); return }
    if (!(price > 0)) { setErr('Sale price must be greater than 0.'); return }
    if (!form.trade_date) { setErr('Date is required.'); return }
    try {
      const res = await sellMut.mutateAsync({
        accountId,
        symbol: selected.symbol,
        exchange: selected.exchange,
        quantity: qty,
        price,
        trade_date: form.trade_date,
      })
      setMsg(res.message)
      setForm({ symbol: '', quantity: '', price: '', trade_date: today })
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to record sale.')
    }
  }

  if (!open) return null

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="card-title">Record a Sale</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        Record shares you sold that the tradebook doesn't have. The position's
        quantity drops at its current average cost (the average is unchanged); a
        fully-sold position moves to the <strong>Exited</strong> tab with its realized P&amp;L.
      </div>
      <form onSubmit={submit} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Holding</label>
          <select className="form-select" style={{ minWidth: 220 }} value={form.symbol}
            onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}>
            <option value="">Select holding…</option>
            {holdings?.map((h) => (
              <option key={`${h.symbol}-${h.exchange}`} value={h.symbol}>
                {h.symbol} ({h.exchange}) — {formatNumber(h.quantity, 0)} @ {formatINR(h.average_price)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Qty {selected ? `(of ${formatNumber(heldQty, 0)})` : ''}</label>
          <input className="form-input" type="number" min="0" max={heldQty || undefined} step="any" style={{ width: 100 }} placeholder="0"
            value={form.quantity} onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Sale Price ₹</label>
          <input className="form-input" type="number" min="0" step="any" style={{ width: 110 }} placeholder="0"
            value={form.price} onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Date</label>
          <input className="form-input" type="date"
            value={form.trade_date} onChange={(e) => setForm((f) => ({ ...f, trade_date: e.target.value }))} />
        </div>
        <button className="btn btn-primary btn-sm" type="submit" disabled={sellMut.isPending}>
          {sellMut.isPending ? 'Recording…' : 'Record Sale'}
        </button>
      </form>
      {selected && qty > 0 && price > 0 && (
        <div style={{ marginTop: 10, fontSize: 13 }}>
          Est. realized: <span className={signClass(estPnl)} style={{ fontFamily: 'var(--font-mono)' }}>{formatINR(estPnl)}</span>
        </div>
      )}
      {err && <div className="error-state" style={{ marginTop: 10 }}>{err}</div>}
      {msg && <div style={{ marginTop: 10, fontSize: 13, color: 'var(--positive)' }}>{msg}</div>}
    </div>
  )
}

// Holdings toolbar: the two manual-entry buttons sit side by side; each form's
// card expands full-width below them, and the two toggle independently.
function HoldingActions() {
  const [addOpen, setAddOpen] = useState(false)
  const [sellOpen, setSellOpen] = useState(false)

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button className="btn btn-secondary btn-sm" onClick={() => setAddOpen((o) => !o)}>
          {addOpen ? 'Close' : '+ Add Shares'}
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => setSellOpen((o) => !o)}>
          {sellOpen ? 'Close' : '− Record Sale'}
        </button>
      </div>
      <AddSharesForm open={addOpen} />
      <RecordSaleForm open={sellOpen} />
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
  // Nullable fields (e.g. isin) sort last regardless of direction.
  if (av == null) return 1
  if (bv == null) return -1
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
  const [editing, setEditing] = useState<Holding | null>(null)

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
      <HoldingActions />
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
                <th style={{ textAlign: 'right' }}>Units</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((h) => (
                <tr key={`${h.account_id}-${h.symbol}-${h.exchange}`}>
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
                  <td style={{ textAlign: 'right' }}>
                    <button type="button" className="link-button" onClick={() => setEditing(h)}>
                      ✎ Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {editing && <HoldingDetailModal holding={editing} onClose={() => setEditing(null)} />}
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
