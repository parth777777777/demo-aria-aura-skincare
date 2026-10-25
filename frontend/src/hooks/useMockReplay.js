import { useCallback, useEffect, useRef, useState } from "react";

export function useMockReplay(dispatch, events, intervalMs = 500) {
  const timerRef = useRef(null);
  const [isRunning, setIsRunning] = useState(false);

  const stopMockReplay = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
      setIsRunning(false);
    }
  }, []);

  const startMockReplay = useCallback(() => {
    stopMockReplay();
    if (!Array.isArray(events) || events.length === 0) return;
    let index = 0;
    const timer = setInterval(() => {
      dispatch(events[index]);
      index += 1;
      if (index >= events.length) {
        clearInterval(timer);
        if (timerRef.current === timer) {
          timerRef.current = null;
          setIsRunning(false);
        }
      }
    }, intervalMs);
    timerRef.current = timer;
    setIsRunning(true);
  }, [dispatch, events, intervalMs, stopMockReplay]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearInterval(timerRef.current);
    };
  }, []);

  return { startMockReplay, stopMockReplay, isRunning };
}
