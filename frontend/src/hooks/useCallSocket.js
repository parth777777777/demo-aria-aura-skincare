import { useCallback, useEffect, useRef } from "react";
import { createCallSocket } from "../lib/callSocket.js";
import { createPcmPlayer } from "../lib/pcmPlayer.js";

export function useCallSocket(onEvent) {
  const eventRef = useRef(onEvent);
  const socketRef = useRef(null);
  const playerRef = useRef(null);
  const contextRef = useRef(null);
  eventRef.current = onEvent;

  const disposeAudio = useCallback(() => {
    const player = playerRef.current;
    playerRef.current = null;
    contextRef.current = null;
    if (player) Promise.resolve(player.close()).catch(() => {});
  }, []);
  const start = useCallback(async () => {
    if (socketRef.current) return;
    let context;
    try {
      context = new AudioContext();
      contextRef.current = context;
      const player = createPcmPlayer(context);
      playerRef.current = player;
      await context.resume();
      if (context.state === "suspended") throw new Error("blocked");
    } catch {
      disposeAudio();
      eventRef.current({
        type: "error",
        code: "AUDIO_BLOCKED",
        message: "Audio playback is blocked by your browser.",
        recoverable: true,
      });
      return;
    }
    let socket;
    socket = createCallSocket({
      url: import.meta.env.VITE_WS_URL,
      onAudio: (data) => playerRef.current?.enqueue(data),
      onEvent: (event) => {
        if (socketRef.current !== socket) return;
        if (event?.type === "interrupted") playerRef.current?.flush();
        eventRef.current(event);
        if (
          event?.type === "connection_lost" ||
          event?.type === "call_cancelled" ||
          (event?.type === "status" && event.state === "ended") ||
          (event?.type === "error" && event.recoverable === false)
        ) {
          socketRef.current = null;
          disposeAudio();
        }
      },
    });
    socketRef.current = socket;
    socket.start();
  }, [disposeAudio]);
  const end = useCallback(() => {
    socketRef.current?.end();
    disposeAudio();
  }, [disposeAudio]);

  useEffect(
    () => () => {
      socketRef.current?.close();
      socketRef.current = null;
      disposeAudio();
    },
    [disposeAudio],
  );

  return {
    start,
    end,
    playTestTone: () => {
      const samples = new Int16Array(24000);
      for (let i = 0; i < samples.length; i++)
        samples[i] = Math.round(
          Math.sin((2 * Math.PI * 440 * i) / 24000) * 12000,
        );
      playerRef.current?.enqueue(samples.buffer);
    },
  };
}
