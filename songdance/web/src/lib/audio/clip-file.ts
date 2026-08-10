import { clipDuration, type AudioClip } from "./clip";

const OUTPUT_SAMPLE_RATE = 44_100;

export async function createClipFile(file: File, clip: AudioClip): Promise<File> {
  const context = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await context.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new Error("无法读取所选片段，请重新选择音频。");
  } finally {
    await context.close();
  }

  const duration = clipDuration(clip);
  const frameCount = Math.max(1, Math.round(duration * OUTPUT_SAMPLE_RATE));
  const offline = new OfflineAudioContext(1, frameCount, OUTPUT_SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start(0, clip.start, duration);
  const rendered = await offline.startRendering();
  const wav = encodeMonoWav(rendered.getChannelData(0), OUTPUT_SAMPLE_RATE);
  const stem = file.name.replace(/\.[^.]+$/, "") || "piano";
  return new File([wav.buffer as ArrayBuffer], `${stem}-clip.wav`, { type: "audio/wav" });
}

export function encodeMonoWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const bytes = new Uint8Array(44 + samples.length * 2);
  const view = new DataView(bytes.buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, bytes.length - 8, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index] ?? 0));
    view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return bytes;
}

function writeAscii(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
