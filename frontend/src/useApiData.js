import { useEffect, useRef, useState } from 'react'

// Stale-while-revalidate: `loading` only blocks the FIRST successful fetch.
// Refetches (deps change, polling) keep showing the last-known `data` and
// just flip `refreshing` so callers can show a subtle indicator instead of
// blanking the whole view back to "Laddar…".
export function useApiData(fetcher, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const hasLoaded = useRef(false)

  useEffect(() => {
    let cancelled = false
    if (hasLoaded.current) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    fetcher()
      .then((result) => {
        if (cancelled) return
        setData(result)
        hasLoaded.current = true
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
        setRefreshing(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading, refreshing }
}
