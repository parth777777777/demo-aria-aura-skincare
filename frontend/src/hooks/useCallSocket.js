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
  updateMicLiveState,
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
  const startCancelledRef = useRef(false);
  const statsRef = useRef({
    frames: 0,
    bytes: 0,
    rejected: { not_live: 0, socket_not_open: 0, buffered_amount: 0 },
    bufferedAmount: 0,
    inputTranscripts: 0,
    outputTranscripts: 0,
    audioBytesReceived: 0,
  });
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
    startCancelledRef.current = false;
    statsRef.current = {
      frames: 0,
      bytes: 0,
      rejected: { not_live: 0, socket_not_open: 0, buffered_amount: 0 },
      bufferedAmount: 0,
      inputTranscripts: 0,
      outputTranscripts: 0,
      audioBytesReceived: 0,
    };
    setStats({ ...statsRef.current });
    let context;
    try {
      context = new AudioContext();
      contextRef.current = context;
      const player = createPcmPlayer(context);
      playerRef.current = player;
      const resumed = context.resume();
      await resumed;
      if (startCancelledRef.current) {
        disposeAudio();
        return;
      }
      if (context.state === "suspended") throw new Error("blocked");
    } catch {
      disposeAudio();
      if (startCancelledRef.current) return;
      eventRef.current({
        type: "error",
        code: "AUDIO_BLOCKED",
        message: "Audio playback is blocked by your browser.",
        recoverable: true,
      });
      eventRef.current({ type: "call_cancelled" });
      return;
    }
    let socket;
    const acquired = await acquireMicThenOpen({
      getUserMedia: navigator.mediaDevices.getUserMedia.bind(
        navigator.mediaDevices,
      ),
      context,
      loadWorklet: (audioContext) =>
        audioContext.audioWorklet.addModule("/mic-worklet.js"),
      shouldCancel: () => startCancelledRef.current,
      openSocket: () => {
        socket = createCallSocket({
          url: import.meta.env.VITE_WS_URL,
          onAudio: (data) => {
            statsRef.current.audioBytesReceived += data.byteLength;
            setStats({ ...statsRef.current });
            playerRef.current?.enqueue(data);
          },
          onEvent: (event) => {
            if (socketRef.current !== socket) return;
            if (event?.type === "transcript") {
              const key =
                event.role === "user"
                  ? "inputTranscripts"
                  : "outputTranscripts";
              statsRef.current[key] += 1;
              setStats({ ...statsRef.current });
            }
            if (event?.type === "interrupted") playerRef.current?.flush();
            eventRef.current(event);
            updateMicLiveState(liveRef, event);
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
        eventRef.current({ type: "call_cancelled" });
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
        statsRef.current.bufferedAmount =
          socket.getWebSocket()?.bufferedAmount ?? 0;
        statsRef.current = {
          ...statsRef.current,
          frames: statsRef.current.frames + 1,
          bytes: statsRef.current.bytes + frame.byteLength,
        };
        setStats({ ...statsRef.current });
      },
      onRejected: (reason, bufferedAmount) => {
        statsRef.current.rejected[reason] += 1;
        statsRef.current.bufferedAmount = bufferedAmount;
        setStats({
          ...statsRef.current,
          rejected: { ...statsRef.current.rejected },
        });
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
    if (!socketRef.current && startLockRef.current.starting) {
      startCancelledRef.current = true;
      disposeAudio();
      eventRef.current({ type: "call_cancelled" });
      return;
    }
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
