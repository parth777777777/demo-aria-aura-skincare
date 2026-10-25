import { useCallback, useEffect, useRef } from "react";
import { createCallSocket } from "../lib/callSocket.js";

export function useCallSocket(onEvent) {
  const eventRef = useRef(onEvent);
  const socketRef = useRef(null);
  eventRef.current = onEvent;

  const start = useCallback(() => {
    if (socketRef.current) return;
    let socket;
    socket = createCallSocket({
      url: import.meta.env.VITE_WS_URL,
      onEvent: (event) => {
        if (socketRef.current !== socket) return;
        eventRef.current(event);
        if (
          event?.type === "connection_lost" ||
          event?.type === "call_cancelled" ||
          (event?.type === "status" && event.state === "ended") ||
          (event?.type === "error" && event.recoverable === false)
        ) socketRef.current = null;
      },
    });
    socketRef.current = socket;
    socket.start();
  }, []);
  const end = useCallback(() => socketRef.current?.end(), []);

  useEffect(() => () => {
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  return { start, end };
}
