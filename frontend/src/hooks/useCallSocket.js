import { useCallback, useEffect, useRef, useState } from "react";
import { createCallSocket } from "../lib/callSocket.js";
import { createPcmPlayer } from "../lib/pcmPlayer.js";
import {
  createFramer,
  createResampler,
  floatToPcm16,
} from "../lib/pcmCapture.js";
import {
  acquireMicThenOpen,
  cleanupMic,
  createFrameGate,
  createStartLock,
  endMicCall,
  onMicTrackEnded,
} from "../lib/micLifecycle.js";

export function useCallSocket(onEvent) {
  const eventRef = useRef(onEvent);
  const socketRef = useRef(null);
  const playerRef = useRef(null);
  const contextRef = useRef(null);
  const streamRef = useRef(null);
  const sourceRef = useRef(null);
  const workletRef = useRef(null);
  const liveRef = useRef(false);
  const statsRef = useRef({ frames: 0, bytes: 0 });
  const startLockRef = useRef(createStartLock());
  const [stats, setStats] = useState({ frames: 0, bytes: 0 });
  eventRef.current = onEvent;

  const disposeAudio = useCallback(() => {
    liveRef.current = false;
    cleanupMic({
      stream: streamRef.current,
      source: sourceRef.current,
      node: workletRef.current,
      context: contextRef.current,
    });
    streamRef.current = null;
    sourceRef.current = null;
    workletRef.current = null;
    const player = playerRef.current;
    playerRef.current = null;
    contextRef.current = null;
    if (player) Promise.resolve(player.close()).catch(() => {});
  }, []);
  const startCall = useCallback(async () => {
    if (socketRef.current) return;
    let context;
    try {
      context = new AudioContext();
      contextRef.current = context;
      const player = createPcmPlayer(context);
      playerRef.current = player;
      const resumed = context.resume();
      await resumed;
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
    const acquired = await acquireMicThenOpen({
      getUserMedia: navigator.mediaDevices.getUserMedia.bind(
        navigator.mediaDevices,
      ),
      context,
      loadWorklet: (audioContext) =>
        audioContext.audioWorklet.addModule(
          new URL("../lib/micWorklet.js", import.meta.url),
        ),
      openSocket: () => {
        socket = createCallSocket({
          url: import.meta.env.VITE_WS_URL,
          onAudio: (data) => playerRef.current?.enqueue(data),
          onEvent: (event) => {
            if (socketRef.current !== socket) return;
            if (event?.type === "interrupted") playerRef.current?.flush();
            eventRef.current(event);
            liveRef.current =
              event?.type === "status" && event.state === "live";
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
        return socket;
      },
      onError: (message) => {
        eventRef.current({
          type: "error",
          code: "MICROPHONE_REQUIRED",
          message,
          recoverable: true,
        });
      },
    });
    if (!acquired) {
      disposeAudio();
      return;
    }
    const { stream } = acquired;
    streamRef.current = stream;
    socketRef.current = socket;
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, "mic-capture");
    const resampler = createResampler(context.sampleRate, 16000);
    const framer = createFramer(320);
    sourceRef.current = source;
    workletRef.current = node;
    const sendFrame = createFrameGate({
      getSocket: () => socket.getWebSocket?.(),
      isLive: () => liveRef.current,
      onSent: (frame) => {
        statsRef.current = {
          frames: statsRef.current.frames + 1,
          bytes: statsRef.current.bytes + frame.byteLength,
        };
        setStats({ ...statsRef.current });
      },
      openState: WebSocket.OPEN,
    });
    node.port.onmessage = ({ data }) => {
      for (const frame of framer.push(floatToPcm16(resampler.process(data)))) {
        sendFrame(frame);
      }
    };
    stream.getTracks().forEach((track) =>
      onMicTrackEnded(track, () => {
        eventRef.current({
          type: "error",
          code: "MICROPHONE_DISCONNECTED",
          message: "Microphone disconnected.",
          recoverable: true,
        });
        endMicCall({
          socket,
          cleanup: disposeAudio,
          onEnded: () => {
            socketRef.current = null;
          },
        });
      }),
    );
    source.connect(node);
    socket.start();
  }, [disposeAudio]);
  const start = useCallback(() => {
    if (socketRef.current || startLockRef.current.starting)
      return Promise.resolve();
    return startLockRef.current.run(startCall);
  }, [startCall]);
  const end = useCallback(() => {
    endMicCall({ socket: socketRef.current, cleanup: disposeAudio });
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
    stats,
  };
}
