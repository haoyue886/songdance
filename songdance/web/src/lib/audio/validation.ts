import { MIN_CLIP_SECONDS } from "./clip";

export const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
export const AUDIO_ACCEPT = ".mp3,.wav,.m4a,audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a";

export type SupportedAudioFormat = "mp3" | "wav" | "m4a";

export type AudioInspection = {
  format: SupportedAudioFormat;
  duration: number;
};

export type AudioInspectionResult =
  | { ok: true; value: AudioInspection }
  | { ok: false; error: string };

type DurationLoader = (file: File) => Promise<number>;

const FORMAT_LABELS: Record<SupportedAudioFormat, string> = {
  mp3: "MP3",
  wav: "WAV",
  m4a: "M4A",
};

const ALLOWED_MIME_TYPES: Record<SupportedAudioFormat, ReadonlySet<string>> = {
  mp3: new Set(["audio/mpeg", "audio/mp3"]),
  wav: new Set(["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"]),
  m4a: new Set(["audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"]),
};

function extensionOf(fileName: string): SupportedAudioFormat | null {
  const extension = fileName.split(".").pop()?.toLowerCase();
  return extension === "mp3" || extension === "wav" || extension === "m4a"
    ? extension
    : null;
}

function ascii(bytes: Uint8Array, start: number, length: number): string {
  return String.fromCharCode(...bytes.slice(start, start + length));
}

export async function sniffAudioFormat(file: File): Promise<SupportedAudioFormat | null> {
  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  if (bytes.length >= 12 && ascii(bytes, 0, 4) === "RIFF" && ascii(bytes, 8, 4) === "WAVE") {
    return "wav";
  }
  if (
    bytes.length >= 3 &&
    (ascii(bytes, 0, 3) === "ID3" || (bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0))
  ) {
    return "mp3";
  }
  if (bytes.length >= 12 && ascii(bytes, 4, 4) === "ftyp") {
    return "m4a";
  }
  return null;
}

async function inspectM4aHandlers(file: File): Promise<{ hasAudio: boolean; hasVideo: boolean }> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const handlers = { hasAudio: false, hasVideo: false };
  parseIsoBoxes(bytes, view, 0, bytes.length, handlers);
  return handlers;
}

const ISO_CONTAINER_BOXES = new Set(["moov", "trak", "mdia"]);

function parseIsoBoxes(
  bytes: Uint8Array,
  view: DataView,
  start: number,
  end: number,
  handlers: { hasAudio: boolean; hasVideo: boolean },
): void {
  let offset = start;
  while (offset + 8 <= end) {
    const size32 = view.getUint32(offset);
    const type = ascii(bytes, offset + 4, 4);
    let headerSize = 8;
    let boxSize = size32;

    if (size32 === 1) {
      if (offset + 16 > end) return;
      const high = view.getUint32(offset + 8);
      const low = view.getUint32(offset + 12);
      if (high > 0x1fffff) return;
      boxSize = high * 2 ** 32 + low;
      headerSize = 16;
    } else if (size32 === 0) {
      boxSize = end - offset;
    }

    if (boxSize < headerSize || offset + boxSize > end) return;
    const payloadStart = offset + headerSize;
    const boxEnd = offset + boxSize;

    if (type === "hdlr" && payloadStart + 12 <= boxEnd) {
      const handlerType = ascii(bytes, payloadStart + 8, 4);
      if (handlerType === "soun") handlers.hasAudio = true;
      if (handlerType === "vide") handlers.hasVideo = true;
    } else if (ISO_CONTAINER_BOXES.has(type)) {
      parseIsoBoxes(bytes, view, payloadStart, boxEnd, handlers);
    }

    if (boxSize === 0) return;
    offset = boxEnd;
  }
}

function declaredMimeError(file: File, format: SupportedAudioFormat): string | null {
  const declaredMime = file.type.toLowerCase().split(";", 1)[0].trim();
  if (!declaredMime || declaredMime === "application/octet-stream") return null;
  if (ALLOWED_MIME_TYPES[format].has(declaredMime)) return null;
  return `文件声明的 MIME 类型 ${declaredMime} 与 ${FORMAT_LABELS[format]} 内容不一致`;
}

export function loadAudioDuration(file: File, timeoutMs = 8_000): Promise<number> {
  return new Promise((resolve, reject) => {
    const audio = new Audio();
    const url = URL.createObjectURL(file);
    const cleanup = () => {
      window.clearTimeout(timeout);
      audio.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("读取音频超时，请重试或换一个文件"));
    }, timeoutMs);

    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      const duration = audio.duration;
      cleanup();
      if (!Number.isFinite(duration) || duration <= 0) {
        reject(new Error("无法读取有效音频时长"));
        return;
      }
      resolve(duration);
    };
    audio.onerror = () => {
      cleanup();
      reject(new Error("浏览器无法解码这个音频文件"));
    };
    audio.src = url;
  });
}

export async function inspectAudioFile(
  file: File,
  durationLoader: DurationLoader = loadAudioDuration,
): Promise<AudioInspectionResult> {
  if (file.size === 0) {
    return { ok: false, error: "文件是空的，请选择有效音频" };
  }
  if (file.size > MAX_AUDIO_BYTES) {
    return { ok: false, error: "文件超过 25 MB，请压缩后重试" };
  }

  const extension = extensionOf(file.name);
  if (!extension) {
    return { ok: false, error: "只支持 MP3、WAV 或 M4A 文件" };
  }

  const detectedFormat = await sniffAudioFormat(file);
  if (!detectedFormat) {
    return { ok: false, error: "文件内容不是可识别的 MP3、WAV 或 M4A 音频" };
  }
  if (detectedFormat !== extension) {
    return {
      ok: false,
      error: `文件扩展名与内容不一致：扩展名是 ${FORMAT_LABELS[extension]}，内容是 ${FORMAT_LABELS[detectedFormat]}`,
    };
  }
  const mimeError = declaredMimeError(file, detectedFormat);
  if (mimeError) {
    return { ok: false, error: mimeError };
  }
  if (detectedFormat === "m4a") {
    const handlers = await inspectM4aHandlers(file);
    if (handlers.hasVideo) {
      return { ok: false, error: "M4A 容器包含视频轨，请导出纯音频后重试" };
    }
    if (!handlers.hasAudio) {
      return { ok: false, error: "无法确认 M4A 容器包含有效音频轨" };
    }
  }

  try {
    const duration = await durationLoader(file);
    if (duration < MIN_CLIP_SECONDS) {
      return { ok: false, error: "音频必须至少 1 秒" };
    }
    return { ok: true, value: { format: detectedFormat, duration } };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "浏览器无法解码这个音频文件",
    };
  }
}
