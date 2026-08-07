"use client";

import { useRef, useState } from "react";
import { AUDIO_ACCEPT } from "@/lib/audio/validation";

type AudioDropzoneProps = {
  disabled?: boolean;
  fileName?: string;
  onFile: (file: File) => void;
};

export function AudioDropzone({ disabled = false, fileName, onFile }: AudioDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const chooseFirstFile = (files: FileList | null) => {
    const file = files?.item(0);
    if (file) onFile(file);
  };

  return (
    <div
      onDragEnter={(event) => {
        event.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        if (!disabled) chooseFirstFile(event.dataTransfer.files);
      }}
      className={`rounded-[1.6rem] border border-dashed p-6 text-center transition sm:p-10 ${
        isDragging ? "border-[#147d70] bg-[#e6f3ee]" : "border-[#a9c9bf] bg-[#fbfcf8]"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={AUDIO_ACCEPT}
        disabled={disabled}
        className="sr-only"
        aria-label="选择钢琴音频"
        onChange={(event) => chooseFirstFile(event.currentTarget.files)}
      />
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#dff0e9] text-[#147d70]">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none">
          <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5 14v3.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </span>
      <p className="mt-4 font-bold">{fileName ?? "拖入钢琴音频，或从电脑选择"}</p>
      <p className="mt-1 text-sm text-[#6a7975]">MP3、WAV、M4A · 最大 25 MB</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="mt-5 rounded-full border border-[#bfd4cc] bg-white px-4 py-2 text-sm font-bold text-[#075e55] hover:border-[#147d70] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {fileName ? "更换文件" : "选择文件"}
      </button>
    </div>
  );
}
