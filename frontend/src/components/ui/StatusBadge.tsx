import type { HoldingStatus, InsightAction } from '../../api/types'

export function HoldingStatusBadge({ status }: { status: HoldingStatus }) {
  const map: Record<HoldingStatus, { cls: string; label: string }> = {
    STRONG_GAIN: { cls: 'badge-strong-gain', label: 'Strong Gain' },
    GAIN:        { cls: 'badge-gain',        label: 'Gain' },
    FLAT:        { cls: 'badge-flat',        label: 'Flat' },
    LOSS:        { cls: 'badge-loss',        label: 'Loss' },
    STRONG_LOSS: { cls: 'badge-strong-loss', label: 'Strong Loss' },
  }
  const { cls, label } = map[status] ?? { cls: 'badge-flat', label: status }
  return <span className={`badge ${cls}`}>{label}</span>
}

export function ActionBadge({ action }: { action: InsightAction }) {
  const map: Record<InsightAction, string> = {
    BUY:  'badge-buy',
    SELL: 'badge-sell',
    HOLD: 'badge-hold',
  }
  return <span className={`badge ${map[action]}`}>{action}</span>
}

type AuthStatusType = 'connected' | 'expired' | 'disconnected'

export function AuthStatusBadge({ status }: { status: AuthStatusType }) {
  const map: Record<AuthStatusType, string> = {
    connected:    'badge-connected',
    expired:      'badge-expired',
    disconnected: 'badge-disconnected',
  }
  return <span className={`badge ${map[status]}`}>{status}</span>
}
