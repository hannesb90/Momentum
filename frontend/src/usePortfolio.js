import { useCallback, useEffect, useState } from 'react'

/**
 * Personlig portfölj sparad lokalt i webbläsaren (localStorage). Systemet är
 * enanvändar/Pi-baserat och har ingen backend-lagring av innehav, så vi håller
 * innehaven på enheten. Varje innehav: { ticker, shares, avgPrice }.
 *
 * OBS: lagras per enhet/webbläsare – inte synkat mellan enheter.
 */
const STORAGE_KEY = 'momentum.holdings.v1'

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

export function usePortfolio() {
  const [holdings, setHoldings] = useState(load)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(holdings))
    } catch {
      // tyst: full localStorage ska inte krascha appen
    }
  }, [holdings])

  const addHolding = useCallback((holding) => {
    const ticker = holding.ticker.trim().toUpperCase()
    if (!ticker) return
    setHoldings((prev) => {
      const existing = prev.find((h) => h.ticker === ticker)
      if (existing) {
        return prev.map((h) =>
          h.ticker === ticker
            ? { ...h, shares: holding.shares ?? h.shares, avgPrice: holding.avgPrice ?? h.avgPrice }
            : h,
        )
      }
      return [...prev, { ticker, shares: holding.shares ?? null, avgPrice: holding.avgPrice ?? null }]
    })
  }, [])

  const removeHolding = useCallback((ticker) => {
    setHoldings((prev) => prev.filter((h) => h.ticker !== ticker))
  }, [])

  return { holdings, addHolding, removeHolding }
}
