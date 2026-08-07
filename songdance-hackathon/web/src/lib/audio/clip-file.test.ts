import { describe, expect, it } from "vitest";
import { encodeMonoWav } from "./clip-file";

describe("clip WAV encoder", () => {
  it("creates a valid mono PCM header and clamps samples", () => {
    const wav = encodeMonoWav(new Float32Array([-2, -0.5, 0, 0.5, 2]), 44_100);
    const view = new DataView(wav.buffer);

    expect(new TextDecoder().decode(wav.slice(0, 4))).toBe("RIFF");
    expect(new TextDecoder().decode(wav.slice(8, 12))).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(44_100);
    expect(view.getUint32(40, true)).toBe(10);
    expect(view.getInt16(44, true)).toBe(-32_768);
    expect(view.getInt16(52, true)).toBe(32_767);
  });
});
