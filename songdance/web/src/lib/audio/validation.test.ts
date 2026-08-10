import { describe, expect, it } from "vitest";
import { inspectAudioFile, MAX_AUDIO_BYTES, sniffAudioFormat } from "./validation";

function audioFile(name: string, bytes: number[], type: string): File {
  return new File([new Uint8Array(bytes)], name, { type });
}

const WAV_HEADER = [
  0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
];
const fourCc = (value: string) => Uint8Array.from(value, (character) => character.charCodeAt(0));

function isoBox(type: string, payload: Uint8Array): Uint8Array {
  const size = payload.length + 8;
  const result = new Uint8Array(size);
  new DataView(result.buffer).setUint32(0, size);
  result.set(fourCc(type), 4);
  result.set(payload, 8);
  return result;
}

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const result = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function makeM4a(handlerType: "soun" | "vide", targetSize?: number): Uint8Array {
  const ftypPayload = new Uint8Array(8);
  ftypPayload.set(fourCc("M4A "));
  const ftyp = isoBox("ftyp", ftypPayload);
  const handlerPayload = new Uint8Array(12);
  handlerPayload.set(fourCc(handlerType), 8);
  const handler = isoBox("hdlr", handlerPayload);
  const moov = isoBox("moov", isoBox("trak", isoBox("mdia", handler)));
  const paddingLength = targetSize ? targetSize - ftyp.length - moov.length - 8 : 0;
  const free = paddingLength > 0 ? isoBox("free", new Uint8Array(paddingLength)) : new Uint8Array();
  return concatBytes(ftyp, free, moov);
}

const M4A_HEADER = Array.from(makeM4a("soun"));
const VIDEO_M4A_HEADER = Array.from(makeM4a("vide"));

describe("audio file inspection", () => {
  it("sniffs supported file signatures", async () => {
    await expect(sniffAudioFormat(audioFile("piano.wav", WAV_HEADER, "audio/wav"))).resolves.toBe("wav");
    await expect(sniffAudioFormat(audioFile("piano.mp3", [0x49, 0x44, 0x33], "audio/mpeg"))).resolves.toBe("mp3");
    await expect(sniffAudioFormat(audioFile("piano.m4a", M4A_HEADER, "audio/mp4"))).resolves.toBe("m4a");
  });

  it("rejects a renamed file whose signature disagrees", async () => {
    const result = await inspectAudioFile(
      audioFile("not-really.mp3", WAV_HEADER, "audio/mpeg"),
      async () => 30,
    );
    expect(result).toEqual({
      ok: false,
      error: "文件扩展名与内容不一致：扩展名是 MP3，内容是 WAV",
    });
  });

  it("rejects a declared MIME type that disagrees with the detected content", async () => {
    const result = await inspectAudioFile(
      audioFile("piano.wav", WAV_HEADER, "audio/mpeg"),
      async () => 30,
    );
    expect(result).toEqual({
      ok: false,
      error: "文件声明的 MIME 类型 audio/mpeg 与 WAV 内容不一致",
    });
  });

  it("accepts audio-only M4A and rejects a container with a video track", async () => {
    await expect(
      inspectAudioFile(audioFile("piano.m4a", M4A_HEADER, "audio/mp4"), async () => 30),
    ).resolves.toMatchObject({ ok: true });
    await expect(
      inspectAudioFile(audioFile("video.m4a", VIDEO_M4A_HEADER, "audio/mp4"), async () => 30),
    ).resolves.toEqual({ ok: false, error: "M4A 容器包含视频轨，请导出纯音频后重试" });
  });

  it("parses a maximum-size M4A by box boundaries within the 3 second budget", async () => {
    const bytes = makeM4a("soun", MAX_AUDIO_BYTES);
    const file = new File(
      [bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer],
      "large.m4a",
      { type: "audio/mp4" },
    );
    const startedAt = performance.now();
    const result = await inspectAudioFile(file, async () => 90);

    expect(result).toMatchObject({ ok: true });
    expect(performance.now() - startedAt).toBeLessThan(3_000);
  });

  it("rejects unsupported, empty, oversized, too-short and undecodable files", async () => {
    await expect(inspectAudioFile(new File([], "empty.wav"), async () => 30)).resolves.toMatchObject({ ok: false });
    const oversized = new File([new Uint8Array(MAX_AUDIO_BYTES + 1)], "large.wav");
    await expect(inspectAudioFile(oversized, async () => 30)).resolves.toMatchObject({ ok: false, error: expect.stringContaining("25 MB") });
    await expect(inspectAudioFile(audioFile("clip.aac", [1, 2, 3], "audio/aac"), async () => 30)).resolves.toMatchObject({ ok: false });
    await expect(inspectAudioFile(audioFile("short.wav", WAV_HEADER, "audio/wav"), async () => 0.5)).resolves.toMatchObject({ ok: false, error: "音频必须至少 1 秒" });
    await expect(inspectAudioFile(audioFile("broken.wav", WAV_HEADER, "audio/wav"), async () => { throw new Error("无法解码"); })).resolves.toEqual({ ok: false, error: "无法解码" });
  });

  it("returns the detected format and decoded duration", async () => {
    const result = await inspectAudioFile(audioFile("piano.wav", WAV_HEADER, "audio/wav"), async () => 42.5);
    expect(result).toEqual({ ok: true, value: { format: "wav", duration: 42.5 } });
  });
});
