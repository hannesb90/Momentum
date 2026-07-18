import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useApiData } from './useApiData'

describe('useApiData', () => {
  it('should be in initial loading state', () => {
    // A fetcher that never resolves to test initial state
    const fetcher = () => new Promise(() => {})
    const { result } = renderHook(() => useApiData(fetcher))

    expect(result.current.loading).toBe(true)
    expect(result.current.refreshing).toBe(false)
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('should fetch data successfully on mount', async () => {
    const fetcher = vi.fn().mockResolvedValue('test data')
    const { result } = renderHook(() => useApiData(fetcher))

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.data).toBe('test data')
    expect(result.current.error).toBeNull()
    expect(result.current.refreshing).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('should handle fetch errors', async () => {
    const error = new Error('fetch failed')
    const fetcher = vi.fn().mockRejectedValue(error)
    const { result } = renderHook(() => useApiData(fetcher))

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe(error)
    expect(result.current.refreshing).toBe(false)
  })

  it('should handle subsequent fetches by setting refreshing state and keeping old data', async () => {
    let resolveFirst, resolveSecond;
    const fetcher = vi.fn()
      .mockImplementationOnce(() => new Promise(res => resolveFirst = res))
      .mockImplementationOnce(() => new Promise(res => resolveSecond = res))

    const { result, rerender } = renderHook(
      ({ deps }) => useApiData(fetcher, deps),
      { initialProps: { deps: [1] } }
    )

    expect(result.current.loading).toBe(true)
    expect(result.current.refreshing).toBe(false)

    // Resolve first fetch
    resolveFirst('data 1')

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.data).toBe('data 1')

    // Trigger dependency change
    rerender({ deps: [2] })

    // It should now be refreshing, not loading, and old data should be kept
    expect(result.current.loading).toBe(false)
    expect(result.current.refreshing).toBe(true)
    expect(result.current.data).toBe('data 1')

    // Resolve second fetch
    resolveSecond('data 2')

    await waitFor(() => {
      expect(result.current.refreshing).toBe(false)
    })

    expect(result.current.data).toBe('data 2')
    expect(result.current.loading).toBe(false)
  })

  it('should not update state if component unmounts before fetch completes', async () => {
    let resolveFetcher;
    const fetcher = vi.fn().mockImplementation(() => new Promise(res => {
      resolveFetcher = res
    }))

    const { result, unmount } = renderHook(() => useApiData(fetcher))

    expect(result.current.loading).toBe(true)

    // Unmount before fetch resolves
    unmount()

    // Resolve fetch
    resolveFetcher('late data')

    // We can't wait for state update since component is unmounted.
    // We just wait a bit to ensure no unhandled promise rejections or state updates occur.
    await new Promise(res => setTimeout(res, 50))

    // State shouldn't have changed to the resolved data
    expect(result.current.data).toBeNull()
  })

  it('should not update state if component unmounts before fetch rejects', async () => {
    let rejectFetcher;
    const fetcher = vi.fn().mockImplementation(() => new Promise((_, rej) => {
      rejectFetcher = rej
    }))

    const { result, unmount } = renderHook(() => useApiData(fetcher))

    expect(result.current.loading).toBe(true)

    unmount()

    // Silence the expected unhandled rejection or catch it in the test environment if needed
    // Vitest usually catches it, but we want to make sure the state is not updated
    rejectFetcher(new Error('late error'))

    await new Promise(res => setTimeout(res, 50))

    expect(result.current.error).toBeNull()
  })
})
