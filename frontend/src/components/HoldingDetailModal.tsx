import { useEffect, useMemo, useState } from 'react'
import type { Holding, Transaction } from '../api/types'
import {
  useHoldingTransactions,
  useCreateTransaction,
  useUpdateTransaction,
  useDeleteTransaction,
} from '../hooks/useTransactions'
import LoadingState from './ui/LoadingState'
import ErrorState from './ui/ErrorState'
import { formatINR, formatNumber, signClass } from '../utils/format'

const TRADE_TYPES = ['buy', 'sell', 'bonus'] as const
const today = () => new Date().toISOString().slice(0, 10)

interface Draft {
  trade_type: string
  quantity: string
  price: string
  trade_date: string
}

const emptyDraft = (): Draft => ({ trade_type: 'buy', quantity: '', price: '', trade_date: today() })

// Cost a row carries, mirroring the backend: qty × price, but a bonus is free.
function amountOf(type: string, qty: number, price: number): number {
  return type === 'bonus' ? 0 : qty * price
}

interface NetPosition {
  quantity: number
  averagePrice: number
  invested: number
}

// Replay the trades with the SAME moving-average convention the backend uses
// (buy/bonus add, sell removes at the running average, a full exit resets cost)
// so the summary stays correct and live as entries are edited.
function deriveNet(txns: Transaction[]): NetPosition {
  const sorted = [...txns].sort((a, b) =>
    a.trade_date < b.trade_date ? -1 : a.trade_date > b.trade_date ? 1 : Number(a.id) - Number(b.id),
  )
  let qty = 0
  let cost = 0
  for (const t of sorted) {
    const type = t.trade_type.toLowerCase()
    if (type === 'buy' || type === 'bonus') {
      qty += t.quantity
      cost += t.amount
    } else if (type === 'sell') {
      if (qty > 0) cost -= t.quantity * (cost / qty)
      qty -= t.quantity
      if (qty <= 1e-9) {
        qty = 0
        cost = 0
      }
    }
  }
  return { quantity: qty, averagePrice: qty > 0 ? cost / qty : 0, invested: qty > 0 ? cost : 0 }
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
        {label}
      </div>
      <div className={className} style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}

interface Props {
  holding: Holding
  onClose: () => void
}

/**
 * View and modify the *unit details* of one holding: the individual buy / sell /
 * bonus trades it is derived from. Each can be edited or deleted, and new ones
 * added — so a wrong entry is correctable and the holding re-derives. Reuses the
 * global `.modal-*` styles (same as the stock-detail popup).
 */
export default function HoldingDetailModal({ holding, onClose }: Props) {
  const accountId = String(holding.account_id)
  const { data: txns, isLoading, isError, error } = useHoldingTransactions(accountId, holding.symbol)

  const createMut = useCreateTransaction()
  const updateMut = useUpdateTransaction()
  const deleteMut = useDeleteTransaction()

  const [add, setAdd] = useState<Draft>(emptyDraft)
  const [editId, setEditId] = useState<string | null>(null)
  const [edit, setEdit] = useState<Draft>(emptyDraft)
  const [err, setErr] = useState('')

  // Escape closes; lock background scroll while open (matches StockModal).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  const net = useMemo(() => deriveNet(txns ?? []), [txns])
  const value = net.quantity * holding.last_price
  const pnl = value - net.invested
  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending

  function startEdit(t: Transaction) {
    setErr('')
    setEditId(String(t.id))
    setEdit({
      trade_type: t.trade_type.toLowerCase(),
      quantity: String(t.quantity),
      price: String(t.price),
      trade_date: t.trade_date,
    })
  }

  function validate(d: Draft): string | null {
    const qty = Number(d.quantity)
    const price = d.trade_type === 'bonus' ? 0 : Number(d.price)
    if (!(qty > 0)) return 'Quantity must be greater than 0.'
    if (!(price >= 0)) return 'Price cannot be negative.'
    if (!d.trade_date) return 'Date is required.'
    return null
  }

  async function submitAdd(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    const problem = validate(add)
    if (problem) { setErr(problem); return }
    try {
      await createMut.mutateAsync({
        account_id: holding.account_id,
        symbol: holding.symbol,
        exchange: holding.exchange,
        isin: holding.isin ?? null,
        trade_type: add.trade_type,
        quantity: Number(add.quantity),
        price: add.trade_type === 'bonus' ? 0 : Number(add.price),
        trade_date: add.trade_date,
      })
      setAdd(emptyDraft())
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to add entry.')
    }
  }

  async function submitEdit() {
    setErr('')
    const problem = validate(edit)
    if (problem) { setErr(problem); return }
    try {
      await updateMut.mutateAsync({
        id: editId!,
        data: {
          trade_type: edit.trade_type,
          quantity: Number(edit.quantity),
          price: edit.trade_type === 'bonus' ? 0 : Number(edit.price),
          trade_date: edit.trade_date,
        },
      })
      setEditId(null)
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to save changes.')
    }
  }

  async function remove(t: Transaction) {
    setErr('')
    if (!window.confirm(`Delete this ${t.trade_type} of ${formatNumber(t.quantity, 0)} ${t.symbol}?`)) return
    try {
      await deleteMut.mutateAsync(String(t.id))
      if (editId === String(t.id)) setEditId(null)
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Failed to delete entry.')
    }
  }

  const cell = { textAlign: 'right' as const, fontFamily: 'var(--font-mono)' }
  const numInput = { width: 80 }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>

        {/* Header + live net summary */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>
            {holding.symbol}
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-muted)', marginLeft: 10, fontFamily: 'var(--font-mono)' }}>
              {holding.exchange}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            Unit details — the trades this holding is derived from. Edit, delete, or add an entry to correct it.
          </div>
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginTop: 14 }}>
            <Stat label="Qty" value={formatNumber(net.quantity, net.quantity % 1 === 0 ? 0 : 2)} />
            <Stat label="Avg Cost" value={formatINR(net.averagePrice)} />
            <Stat label="Invested" value={formatINR(net.invested)} />
            {holding.last_price > 0 && (
              <>
                <Stat label="LTP" value={formatINR(holding.last_price)} />
                <Stat label="Cur Value" value={formatINR(value)} />
                <Stat label="P&L" value={formatINR(pnl)} className={signClass(pnl)} />
              </>
            )}
          </div>
        </div>

        {isLoading && <LoadingState message="Loading trades…" />}
        {isError && <ErrorState error={error} context="Trades" />}

        {txns && (
          <div className="card" style={{ padding: 0 }}>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th style={{ textAlign: 'right' }}>Qty</th>
                    <th style={{ textAlign: 'right' }}>Price</th>
                    <th style={{ textAlign: 'right' }}>Amount</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {txns.length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 20 }}>
                        No trades yet. Add the first entry below.
                      </td>
                    </tr>
                  )}
                  {txns.map((t) =>
                    editId === String(t.id) ? (
                      <tr key={t.id}>
                        <td>
                          <input className="form-input" type="date" value={edit.trade_date}
                            onChange={(e) => setEdit((d) => ({ ...d, trade_date: e.target.value }))} />
                        </td>
                        <td>
                          <select className="form-select" value={edit.trade_type}
                            onChange={(e) => setEdit((d) => ({ ...d, trade_type: e.target.value }))}>
                            {TRADE_TYPES.map((tt) => <option key={tt} value={tt}>{tt}</option>)}
                          </select>
                        </td>
                        <td style={cell}>
                          <input className="form-input" type="number" min="0" step="any" style={numInput}
                            value={edit.quantity} onChange={(e) => setEdit((d) => ({ ...d, quantity: e.target.value }))} />
                        </td>
                        <td style={cell}>
                          <input className="form-input" type="number" min="0" step="any" style={numInput}
                            disabled={edit.trade_type === 'bonus'}
                            value={edit.trade_type === 'bonus' ? '0' : edit.price}
                            onChange={(e) => setEdit((d) => ({ ...d, price: e.target.value }))} />
                        </td>
                        <td style={cell}>
                          {formatINR(amountOf(edit.trade_type, Number(edit.quantity) || 0, Number(edit.price) || 0))}
                        </td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button className="btn btn-primary btn-sm" onClick={submitEdit} disabled={busy}>Save</button>{' '}
                          <button className="btn btn-secondary btn-sm" onClick={() => setEditId(null)} disabled={busy}>Cancel</button>
                        </td>
                      </tr>
                    ) : (
                      <tr key={t.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{t.trade_date}</td>
                        <td style={{ textTransform: 'capitalize' }}>{t.trade_type}</td>
                        <td style={cell}>{formatNumber(t.quantity, t.quantity % 1 === 0 ? 0 : 2)}</td>
                        <td style={cell}>{t.trade_type.toLowerCase() === 'bonus' ? '—' : formatINR(t.price)}</td>
                        <td style={cell}>{formatINR(t.amount)}</td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button className="link-button" onClick={() => startEdit(t)} disabled={busy}>Edit</button>{' '}
                          <button className="link-button" style={{ color: 'var(--negative)' }} onClick={() => remove(t)} disabled={busy}>Delete</button>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
                {/* Add-entry row */}
                <tfoot>
                  <tr>
                    <td>
                      <input className="form-input" type="date" value={add.trade_date}
                        onChange={(e) => setAdd((d) => ({ ...d, trade_date: e.target.value }))} />
                    </td>
                    <td>
                      <select className="form-select" value={add.trade_type}
                        onChange={(e) => setAdd((d) => ({ ...d, trade_type: e.target.value }))}>
                        {TRADE_TYPES.map((tt) => <option key={tt} value={tt}>{tt}</option>)}
                      </select>
                    </td>
                    <td style={cell}>
                      <input className="form-input" type="number" min="0" step="any" style={numInput} placeholder="Qty"
                        value={add.quantity} onChange={(e) => setAdd((d) => ({ ...d, quantity: e.target.value }))} />
                    </td>
                    <td style={cell}>
                      <input className="form-input" type="number" min="0" step="any" style={numInput} placeholder="Price"
                        disabled={add.trade_type === 'bonus'}
                        value={add.trade_type === 'bonus' ? '0' : add.price}
                        onChange={(e) => setAdd((d) => ({ ...d, price: e.target.value }))} />
                    </td>
                    <td style={cell}>
                      {formatINR(amountOf(add.trade_type, Number(add.quantity) || 0, Number(add.price) || 0))}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-primary btn-sm" onClick={submitAdd} disabled={busy}>
                        {createMut.isPending ? 'Adding…' : '+ Add'}
                      </button>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        )}

        {err && <div className="error-state" style={{ marginTop: 12 }}>{err}</div>}
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>
          A <strong>bonus</strong> is free (price ignored): it raises quantity and dilutes the average. A
          <strong> sell</strong> reduces quantity at the running average. Changes re-derive this holding immediately.
        </div>
      </div>
    </div>
  )
}
