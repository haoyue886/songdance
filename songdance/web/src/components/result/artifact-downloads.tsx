"use client";

import { Download, FileMusic, FileText, LoaderCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ArtifactType, JobArtifact } from "@/lib/api/jobs";

type DownloadKind = "raw_midi" | "midi" | "musicxml" | "pdf";

export function ArtifactDownloads({
  artifacts,
  busy,
  musicXmlReady,
  pdfReady,
  onDownload,
}: {
  artifacts: JobArtifact[];
  busy: DownloadKind | null;
  musicXmlReady: boolean;
  pdfReady: boolean;
  onDownload: (kind: DownloadKind) => void;
}) {
  const t = useTranslations("result");
  const midi = artifactState(artifacts, "midi", t("notGenerated"), t("generationFailed"));
  const rawMidi = artifactState(artifacts, "raw_midi", t("notGenerated"), t("generationFailed"));
  const musicXml = artifactState(artifacts, "musicxml", t("notGenerated"), t("generationFailed"));
  return (
    <aside aria-label={t("export")} className="min-w-0">
      <h2 className="text-sm font-bold uppercase text-[#667772]">{t("export")}</h2>
      <div className="mt-3 grid gap-2">
        <DownloadButton label={t("rawMidi")} detail={rawMidi.detail}
          disabled={!rawMidi.available || busy !== null} busy={busy === "raw_midi"}
          icon={<FileMusic size={17} />} onClick={() => onDownload("raw_midi")} />
        <DownloadButton
          label={t("cleanedMidi")}
          detail={midi.detail}
          disabled={!midi.available || busy !== null}
          busy={busy === "midi"}
          icon={<FileMusic size={17} />}
          onClick={() => onDownload("midi")}
        />
        <DownloadButton
          label="MusicXML"
          detail={musicXml.available && !musicXmlReady ? t("previewUnavailable") : musicXml.detail}
          disabled={!musicXml.available || !musicXmlReady || busy !== null}
          busy={busy === "musicxml"}
          icon={<FileMusic size={17} />}
          onClick={() => onDownload("musicxml")}
        />
        <DownloadButton
          label="PDF"
          detail={pdfReady ? t("currentScore") : t("waitingScore")}
          disabled={!pdfReady || busy !== null}
          busy={busy === "pdf"}
          icon={<FileText size={17} />}
          onClick={() => onDownload("pdf")}
        />
      </div>
    </aside>
  );
}

function artifactState(artifacts: JobArtifact[], type: ArtifactType, missing: string, failed: string) {
  const artifact = artifacts.find((item) => item.type === type);
  if (!artifact) return { available: false, detail: missing };
  if (artifact.status === "failed") {
    return { available: false, detail: failed };
  }
  return { available: true, detail: formatBytes(artifact.size_bytes) };
}

function DownloadButton({
  label,
  detail,
  disabled,
  busy,
  icon,
  onClick,
}: {
  label: string;
  detail: string;
  disabled: boolean;
  busy: boolean;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="flex min-h-14 w-full items-center gap-3 rounded-lg border border-[#cad8d2] bg-white px-3 text-left transition hover:border-[#147d70] disabled:cursor-not-allowed disabled:opacity-45"
      disabled={disabled}
      onClick={onClick}
    >
      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-[#edf4f0] text-[#075e55]">
        {busy ? <LoaderCircle className="animate-spin" size={17} /> : icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-bold text-[#15332f]">{label}</span>
        <span className="block truncate text-xs text-[#667772]">{detail}</span>
      </span>
      <Download aria-hidden="true" size={16} className="shrink-0 text-[#667772]" />
    </button>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}
