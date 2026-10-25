export function createCallSocket({
  url,
  onEvent,
  onAudio = () => {},
  WebSocketImpl = WebSocket,
}) {
  let socket = null;
  let started = false;
  let ended = false;
  let fatalError = false;
  let closed = false;

  const connectionLost = () => {
    if (ended || fatalError || closed) return;
    closed = true;
    onEvent({ type: "connection_lost" });
  };

  return {
    start() {
      if (started || closed) return;
      started = true;
      socket = new WebSocketImpl(url);
      socket.binaryType = "arraybuffer";
      socket.addEventListener("open", () => {
        if (!closed) socket.send(JSON.stringify({ type: "start_call" }));
      });
      socket.addEventListener("message", (message) => {
        if (closed) return;
        if (typeof message.data !== "string") {
          onAudio(message.data);
          return;
        }
        let event;
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        if (event?.type === "status" && event.state === "ended") ended = true;
        if (event?.type === "error" && event.recoverable === false)
          fatalError = true;
        onEvent(event);
      });
      socket.addEventListener("close", () => {
        if (closed) return;
        connectionLost();
      });
      socket.addEventListener("error", () => {
        if (closed) return;
        connectionLost();
      });
    },
    end() {
      if (socket?.readyState === WebSocketImpl.CONNECTING) {
        closed = true;
        socket.close();
        onEvent({ type: "call_cancelled" });
        return;
      }
      if (socket?.readyState === WebSocketImpl.OPEN) {
        socket.send(JSON.stringify({ type: "end_call" }));
      }
    },
    close() {
      closed = true;
      if (socket && socket.readyState !== WebSocketImpl.CLOSED) socket.close();
    },
  };
}
