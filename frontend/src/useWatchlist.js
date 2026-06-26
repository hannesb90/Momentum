import { useCallback, useEffect, useState } from 'react'

/**
 * Bevakningslista – tickers man vill följa noggrannare utan att nödvändigtvis
 * äga dem (skiljer sig från usePortfolio: inga antal/inköpspris, bara ticker).
 * Sparas lokalt i webbläsaren, samma begränsning som portföljen: inte synkat
 * mellan enheter.
 */
const STORAGE_KEY = 'momentum.watchlist.v1'

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useWatchlist() {
  const [tickers, setTickers] = useState(load)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tickers))
    } catch {
      // tyst: full localStorage ska inte krascha appen
    }
  }, [tickers])

  const addToWatchlist = useCallback((ticker) => {
    const t = ticker.trim().toUpperCase()
    if (!t) return
    setTickers((prev) => (prev.includes(t) ? prev : [...prev, t]))
  }, [])

  const removeFromWatchlist = useCallback((ticker) => {
    setTickers((prev) => prev.filter((t) => t !== ticker))
  }, [])

  return { tickers, addToWatchlist, removeFromWatchlist }
}
