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

// Snyggar till bolagsnamn för visning: tar bort juridiska suffix som
// "AB (publ.)", "(publ)", "AB" i slutet. Faller tillbaka på tickern om namn
// saknas (t.ex. gammal signals.csv utan namn-kolumn).
export function cleanName(name, ticker) {
  if (!name || name === ticker) return ticker ?? name ?? ''
  return String(name)
    .replace(/\s*\(publ\.?\)\s*$/i, '')
    .replace(/\s+AB\s*$/i, '')
    .trim() || (ticker ?? name)
}
