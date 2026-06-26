const BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  health: () => getJson('/health'),
  stats: () => getJson('/stats'),
  latestSignals: () => getJson('/signals/latest'),
  signalHistory: (ticker, limit = 260) =>
    getJson(`/signals/history?${ticker ? `ticker=${encodeURIComponent(ticker)}&` : ''}limit=${limit}`),
  portfolio: (limit = 1000) => getJson(`/portfolio?limit=${limit}`),
  drift: (limit = 260) => getJson(`/drift?limit=${limit}`),
  regime: () => getJson('/regime'),
  sectorMomentum: () => getJson('/sector-momentum'),
}
