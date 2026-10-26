export const MICROPHONE_ERROR =
  "Microphone access is needed to talk to Aria. Check your browser's permission and try again.";

export function updateMicLiveState(liveRef, event) {
  if (event?.type === "status") liveRef.current = event.state === "live";
}

export function createFrameGate({
  getSocket,
  isLive,
  onSent,
  onRejected,
  openState = 1,
}) {
  return (frame) => {
    const socket = getSocket();
    const reason = !isLive()
      ? "not_live"
      : socket?.readyState !== openState
        ? "socket_not_open"
        : socket.bufferedAmount > 256 * 1024
          ? "buffered_amount"
          : null;
    if (reason) {
      onRejected?.(reason, socket?.bufferedAmount ?? 0);
      return false;
    }
    socket.send(frame);
    onSent?.(frame);
    return true;
  };
}

export function cleanupMic({ stream, source, node, context }) {
  stream?.getTracks().forEach((track) => track.stop());
  source?.disconnect();
  if (node) {
    node.port.onmessage = null;
    node.port.close();
    node.disconnect();
  }
  if (context && context.state !== "closed")
    Promise.resolve(context.close()).catch(() => {});
}

export async function acquireMicThenOpen({
  getUserMedia,
  context,
  loadWorklet,
  openSocket,
  onError,
  shouldCancel = () => false,
}) {
  let stream;
  try {
    stream = await getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (shouldCancel()) {
      cleanupMic({ stream, context });
      return null;
    }
    await loadWorklet(context);
    if (shouldCancel()) {
      cleanupMic({ stream, context });
      return null;
    }
    return { stream, socket: openSocket() };
  } catch {
    cleanupMic({ stream, context });
    if (!shouldCancel()) onError(MICROPHONE_ERROR);
    return null;
  }
}

export function createStartLock() {
  let starting = false;
  return {
    run(start) {
      if (starting) return Promise.resolve();
      starting = true;
      return Promise.resolve()
        .then(start)
        .finally(() => {
          starting = false;
        });
    },
    get starting() {
      return starting;
    },
  };
}

export function endMicCall({ socket, cleanup, onEnded }) {
  socket?.end();
  cleanup();
  onEnded?.();
}

export function onMicTrackEnded(track, callback) {
  track.addEventListener("ended", callback, { once: true });
}
