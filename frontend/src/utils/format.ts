const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

const INR_COMPACT = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  notation: 'compact',
  maximumFractionDigits: 2,
})

const PCT = new Intl.NumberFormat('en-IN', {
  style: 'percent',
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
})

export function formatINR(value: number): string {
  return INR.format(value)
}

export function formatINRCompact(value: number): string {
  return INR_COMPACT.format(value)
}

/** Rupee price without forced decimals, e.g. 1870 -> ₹1,870, 18.5 -> ₹18.5 */
export function formatPrice(value: number): string {
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

export function formatPct(value: number): string {
  return PCT.format(value / 100)
}

/** Format XIRR which comes as a decimal e.g. 0.184 -> 18.40% */
export function formatXIRR(value: number | null): string {
  if (value === null || value === undefined) return 'N/A'
  return PCT.format(value)
}

export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(value)
}

export function signClass(value: number): string {
  if (value > 0) return 'positive'
  if (value < 0) return 'negative'
  return 'neutral'
}
