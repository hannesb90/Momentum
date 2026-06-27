const BASE = import.meta.env.VITE_API_BASE ?? '/api'

// Aktivt segment (storbolag/småbolag). Sätts av segment-toggeln och bifogas
// AUTOMATISKT på varje API-anrop, så sidorna behöver inte känna till segment.
let currentSegment = 'large'
export function setApiSegment(s) {
  if (s) currentSegment = s
}

async function getJson(path) {
  const sep = path.includes('?') ? '&' : '?'
  const res = await fetch(`${BASE}${path}${sep}segment=${encodeURIComponent(currentSegment)}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  segments: () => getJson('/segments'),
  health: () => getJson('/health'),
  stats: () => getJson('/stats'),
  latestSignals: () => getJson('/signals/latest'),
  signalHistory: (ticker, limit = 260) =>
    getJson(`/signals/history?${ticker ? `ticker=${encodeURIComponent(ticker)}&` : ''}limit=${limit}`),
  portfolio: (limit = 1000) => getJson(`/portfolio?limit=${limit}`),
  drift: (limit = 260) => getJson(`/drift?limit=${limit}`),
  regime: () => getJson('/regime'),
  sectorMomentum: () => getJson('/sector-momentum'),
  paperLedger: (limit = 520) => getJson(`/paper-ledger?limit=${limit}`),
  prices: (ticker, limit = 260) =>
    getJson(`/prices?ticker=${encodeURIComponent(ticker)}&limit=${limit}`),
}
