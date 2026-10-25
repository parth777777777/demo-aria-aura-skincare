export function floatToPcm16(input) {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const value = Number.isNaN(input[i])
      ? 0
      : Math.max(-1, Math.min(1, input[i]));
    output[i] =
      value < 0 ? Math.round(value * 32768) : Math.round(value * 32767);
  }
  return output;
}

export function createResampler(inputRate, outputRate = 16000) {
  let buffer = new Float32Array(0);
  let position = 0;
  return {
    process(input) {
      if (inputRate === outputRate) return new Float32Array(input);
      const joined = new Float32Array(buffer.length + input.length);
      joined.set(buffer);
      joined.set(input, buffer.length);
      const step = inputRate / outputRate;
      const result = [];
      while (position + 1 < joined.length) {
        const index = Math.floor(position);
        const fraction = position - index;
        result.push(
          joined[index] * (1 - fraction) + joined[index + 1] * fraction,
        );
        position += step;
      }
      const consumed = Math.floor(position);
      buffer = joined.slice(consumed);
      position -= consumed;
      return Float32Array.from(result);
    },
  };
}

export function createFramer(samplesPerFrame) {
  let pending = new Int16Array(0);
  return {
    push(samples) {
      const joined = new Int16Array(pending.length + samples.length);
      joined.set(pending);
      joined.set(samples, pending.length);
      const frames = [];
      let offset = 0;
      while (offset + samplesPerFrame <= joined.length) {
        const frame = joined.subarray(offset, offset + samplesPerFrame);
        const bytes = new ArrayBuffer(samplesPerFrame * 2);
        const view = new DataView(bytes);
        frame.forEach((sample, i) => view.setInt16(i * 2, sample, true));
        frames.push(bytes);
        offset += samplesPerFrame;
      }
      pending = joined.slice(offset);
      return frames;
    },
  };
}
