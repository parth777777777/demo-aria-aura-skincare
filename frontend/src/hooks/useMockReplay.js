import { useCallback, useEffect, useRef } from 'react'

export function useMockReplay(dispatch, events, intervalMs = 500) {
  const timerRef = useRef(null)

  const stopMockReplay = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!Array.isArray(events) || events.length === 0) return undefined
    let index = 0
    const timer = setInterval(() => {
      dispatch(events[index])
      index += 1
      if (index >= events.length) {
        clearInterval(timer)
        if (timerRef.current === timer) timerRef.current = null
      }
    }, intervalMs)
    timerRef.current = timer
    return () => {
      clearInterval(timer)
      if (timerRef.current === timer) timerRef.current = null
    }
  }, [dispatch, events, intervalMs, stopMockReplay])

  return stopMockReplay
}
