import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobArtifact } from "@/lib/api/jobs";
import { ArtifactDownloads } from "./artifact-downloads";

const artifacts: JobArtifact[] = [
  {
    type: "midi",
    status: "succeeded",
    size_bytes: 2048,
    mime_type: "audio/midi",
    error_code: null,
  },
  {
    type: "musicxml",
    status: "failed",
    size_bytes: 0,
    mime_type: "application/vnd.recordare.musicxml+xml",
    error_code: "MUSICXML_GENERATION_FAILED",
  },
];

describe("artifact downloads", () => {
  it("keeps MIDI available when MusicXML and PDF are unavailable", async () => {
    const download = vi.fn();
    const user = userEvent.setup();
    render(
      <ArtifactDownloads
        artifacts={artifacts}
        busy={null}
        musicXmlReady={false}
        pdfReady={false}
        onDownload={download}
      />,
    );

    const midi = screen.getByRole("button", { name: /^清洗后 MIDI/ });
    expect(midi).toBeEnabled();
    expect(screen.getByRole("button", { name: /^MusicXML/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^PDF/ })).toBeDisabled();
    expect(screen.getByText("MUSICXML_GENERATION_FAILED")).toBeInTheDocument();
    await user.click(midi);
    expect(download).toHaveBeenCalledWith("midi");
  });
});
