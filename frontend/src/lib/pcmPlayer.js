export function createPcmPlayer(audioContext) {
  let nextStartTime = 0;
  let leftover = null;
  const sources = [];
  function flush() {
    for (const source of sources) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
    }
    sources.length = 0;
    nextStartTime = 0;
    leftover = null;
  }
  return {
    enqueue(arrayBuffer) {
      const incoming = new Uint8Array(arrayBuffer);
      if (!incoming.length) return;
      const bytes = new Uint8Array(incoming.length + (leftover ? 1 : 0));
      let offset = 0;
      if (leftover !== null) {
        bytes[0] = leftover;
        offset = 1;
        leftover = null;
      }
      bytes.set(incoming, offset);
      if (bytes.length % 2) leftover = bytes[bytes.length - 1];
      const usableLength = bytes.length - (bytes.length % 2);
      if (!usableLength) return;
      const view = new DataView(bytes.buffer, 0, usableLength);
      const samples = new Float32Array(usableLength / 2);
      for (let i = 0; i < samples.length; i++)
        samples[i] = view.getInt16(i * 2, true) / 32768;
      const buffer = audioContext.createBuffer(1, samples.length, 24000);
      buffer.copyToChannel(samples, 0);
      const source = audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(audioContext.destination);
      const startAt = Math.max(audioContext.currentTime + 0.05, nextStartTime);
      nextStartTime = startAt + buffer.duration;
      sources.push(source);
      source.addEventListener(
        "ended",
        () => {
          const index = sources.indexOf(source);
          if (index >= 0) sources.splice(index, 1);
        },
        { once: true },
      );
      source.start(startAt);
    },
    flush,
    close() {
      flush();
      if (audioContext.state !== "closed") return audioContext.close();
    },
  };
}
