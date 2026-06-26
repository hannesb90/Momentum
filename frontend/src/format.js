export function fmtPct(v, digits = 1) {
  return v == null || Number.isNaN(Number(v)) ? '–' : `${(Number(v) * 100).toFixed(digits)}%`
}

export function fmtNum(v, digits = 2) {
  return v == null || Number.isNaN(Number(v)) ? '–' : Number(v).toFixed(digits)
}

export function fmtSek(v) {
  return v == null ? '–' : `${Number(v).toLocaleString('sv-SE', { maximumFractionDigits: 0 })} kr`
}

export function fmtDate(d) {
  return new Date(d).toLocaleDateString('sv-SE', { year: '2-digit', month: 'short' })
}

export function toneForSignedPct(v) {
  if (v == null) return 'neutral'
  return Number(v) >= 0 ? 'good' : 'bad'
}
