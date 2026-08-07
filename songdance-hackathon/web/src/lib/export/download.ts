export function downloadBytes(
  bytes: string | ArrayBuffer | Uint8Array,
  mimeType: string,
  filename: string,
): void {
  const content = bytes instanceof Uint8Array ? copyBuffer(bytes) : bytes;
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function copyBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}
