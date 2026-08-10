import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TranscriptionJob } from "@/lib/api/jobs";
import type { NoteTimeline } from "@/lib/result/timeline";
import { ResultClient } from "./result-client";

const mocks = vi.hoisted(() => ({
  fetchArtifact: vi.fn(),
  fetchTimeline: vi.fn(),
  getDownloadUrl: vi.fn(),
  play: vi.fn(),
  trackEvent: vi.fn(),
  writeText: vi.fn(),
}));

vi.mock("@/lib/analytics/events", () => ({ trackEvent: mocks.trackEvent }));

vi.mock("@/lib/api/jobs", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api/jobs")>();
  return {
    ...original,
    fetchArtifact: mocks.fetchArtifact,
    getDownloadUrl: mocks.getDownloadUrl,
  };
});

vi.mock("@/lib/result/timeline", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/result/timeline")>();
  return { ...original, fetchTimeline: mocks.fetchTimeline };
});

vi.mock("@/components/result/score-viewer", () => ({
  ScoreViewer: () => <div aria-label="MusicXML 五线谱">rendered score</div>,
}));

vi.mock("@/hooks/use-result-playback", () => ({
  useResultPlayback: () => ({
    audioRef: { current: null },
    duration: 2,
    mode: "midi",
    setMode: vi.fn(),
    playing: false,
    play: mocks.play,
    pause: vi.fn(),
    currentTime: 0,
    seek: vi.fn(),
    rate: 1,
    setRate: vi.fn(),
    loopEnabled: false,
    setLoopEnabled: vi.fn(),
    loopStart: 0,
    setLoopStart: vi.fn(),
    loopEnd: 2,
    setLoopEnd: vi.fn(),
    transpose: 0,
    setTranspose: vi.fn(),
    error: null,
  }),
}));

const timeline: NoteTimeline = {
  schema_version: 1,
  model_version: "test",
  tempo_bpm: 120,
  time_signature: "4/4",
  quality_flags: [],
  notes: [
    {
      id: "note-1",
      start_sec: 0,
      end_sec: 2,
      pitch: 60,
      velocity: 90,
      confidence: 0.9,
      hand: "right",
    },
  ],
};

const job: TranscriptionJob = {
  id: "secure-job",
  status: "succeeded",
  stage: "completed",
  source_type: "upload",
  start_sec: 0,
  end_sec: 2,
  attempt_count: 1,
  error_code: null,
  error_message: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:10Z",
  expires_at: "2026-07-30T00:00:00Z",
  result: {
    tempo: 120,
    time_signature: "4/4",
    note_count: 1,
    quality_flags: "[]",
    model_version: "test",
  },
  quality_report: null,
  artifacts: [
    {
      type: "midi",
      status: "succeeded",
      size_bytes: 100,
      mime_type: "audio/midi",
      error_code: null,
    },
    {
      type: "musicxml",
      status: "succeeded",
      size_bytes: 200,
      mime_type: "application/vnd.recordare.musicxml+xml",
      error_code: null,
    },
    {
      type: "timeline",
      status: "succeeded",
      size_bytes: 300,
      mime_type: "application/json",
      error_code: null,
    },
  ],
};

const qualitySummary = {
  schema_version: 4,
  quality_report_version: "quality-report-v6",
  postprocess_version: "cleanup-v3/analysis-v2/score-v4",
  raw_note_count: 4,
  cleaned_note_count: 3,
  cleanup: {
    status: "applied",
    version: "cleanup-v3",
    removed_note_count: 1,
    clipped_note_count: 0,
    merged_note_count: 0,
    fallback_used: false,
    error_code: null,
  },
  analysis: {
    status: "analyzed",
    version: "analysis-v2",
    bpm: 120,
    bpm_confidence: 0.8,
    time_signature: "4/4",
    time_signature_confidence: 0.7,
    time_signature_source: "detected",
    key_signature: "C major",
    key_confidence: 0.6,
    key_signature_source: "detected",
    reason_codes: [],
  },
  confidence: { min: 0.4, max: 0.95, mean: 0.81 },
  model: { version: "model-v1", thresholds: {} },
  reconstruction: { status: "reconstructed", fallback_used: false, error_code: null },
  musicxml_parse: { status: "passed" },
  structure_errors: [],
};

function withQuality(summary: object = qualitySummary): TranscriptionJob {
  return {
    ...job,
    quality_report: {
      report_version: "quality-report-v6",
      summary: JSON.stringify(summary),
    },
  };
}

describe("result workspace", () => {
  beforeEach(() => {
    mocks.fetchArtifact.mockReset();
    mocks.fetchTimeline.mockReset();
    mocks.getDownloadUrl.mockReset();
    mocks.play.mockReset().mockResolvedValue(true);
    mocks.trackEvent.mockReset();
    mocks.writeText.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
    mocks.fetchTimeline.mockResolvedValue(timeline);
    mocks.fetchArtifact.mockResolvedValue(new Response("<score-partwise/>"));
    mocks.getDownloadUrl.mockResolvedValue("http://api.test/signed-source");
  });

  it("loads the shared timeline and defaults to the score view", async () => {
    render(<ResultClient job={job} deleting={false} onDelete={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "钢琴转录结果" })).toBeInTheDocument();
    expect(screen.getByLabelText("MusicXML 五线谱")).toBeInTheDocument();
    expect(screen.getByText("120.0 BPM")).toBeInTheDocument();
    expect(mocks.fetchTimeline).toHaveBeenCalledWith("secure-job", "timeline", expect.any(AbortSignal));
  });

  it("shows real cleanup, confidence and version data from the quality report", async () => {
    render(<ResultClient job={withQuality()} deleting={false} onDelete={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "钢琴转录结果" })).toBeInTheDocument();
    expect(screen.getByText("4 / 3")).toBeInTheDocument();
    expect(screen.getByText("1 次")).toBeInTheDocument();
    expect(screen.getByText("81%")).toBeInTheDocument();
    expect(screen.getByText("cleanup-v3/analysis-v2/score-v4")).toBeInTheDocument();
    expect(screen.getByText("当前预览：清洗后音符")).toBeInTheDocument();
  });

  it("shows backend low-confidence defaults as warnings", async () => {
    const lowConfidence = {
      ...qualitySummary,
      analysis: {
        ...qualitySummary.analysis,
        bpm_confidence: 0,
        time_signature_confidence: 0.3,
        key_confidence: 0.1,
        reason_codes: [
          "TEMPO_DEFAULTED",
          "TIME_SIGNATURE_DEFAULTED_4_4",
          "KEY_SIGNATURE_DEFAULTED_C_MAJOR",
        ],
      },
    };
    render(<ResultClient job={withQuality(lowConfidence)} deleting={false} onDelete={vi.fn()} />);

    expect(await screen.findByText("BPM 置信度不足，当前速度为系统默认值。")).toBeInTheDocument();
    expect(screen.getByText("拍号置信度不足，当前按 4/4 排版。")).toBeInTheDocument();
    expect(screen.getByText("调性置信度不足，当前按 C major 排版。")).toBeInTheDocument();
  });

  it("falls back to the piano roll when MusicXML cannot be loaded", async () => {
    mocks.fetchArtifact.mockRejectedValue(new Error("storage unavailable"));
    render(<ResultClient job={job} deleting={false} onDelete={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("钢琴卷帘和 MIDI 下载仍可使用");
    expect(screen.getByRole("img", { name: /钢琴卷帘/ })).toBeInTheDocument();
  });

  it("uses the raw timeline when cleanup falls back even if the derived timeline succeeded", async () => {
    const fallbackJob: TranscriptionJob = {
      ...withQuality({
        ...qualitySummary,
        cleanup: { ...qualitySummary.cleanup, status: "failed", fallback_used: true },
      }),
      artifacts: [
        { type: "raw_midi", status: "succeeded", size_bytes: 100, mime_type: "audio/midi", error_code: null },
        { type: "raw_timeline", status: "succeeded", size_bytes: 300, mime_type: "application/json", error_code: null },
        { type: "timeline", status: "succeeded", size_bytes: 300, mime_type: "application/json", error_code: null },
        { type: "musicxml", status: "succeeded", size_bytes: 200, mime_type: "application/xml", error_code: null },
      ],
    };
    render(<ResultClient job={fallbackJob} deleting={false} onDelete={vi.fn()} />);

    expect(await screen.findByText("当前预览：原始模型音符（清洗结果不可用）")).toBeInTheDocument();
    expect(mocks.fetchTimeline).toHaveBeenCalledWith("secure-job", "raw_timeline", expect.any(AbortSignal));
    expect(mocks.fetchArtifact).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: /钢琴卷帘/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "五线谱" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^MusicXML/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^PDF/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^原始 MIDI/ })).toBeEnabled();
  });

  it("refreshes an expired signed source URL when the audio element rejects it", async () => {
    mocks.getDownloadUrl
      .mockResolvedValueOnce("http://api.test/expired-source")
      .mockResolvedValueOnce("http://api.test/refreshed-source");
    const { container } = render(
      <ResultClient job={job} deleting={false} onDelete={vi.fn()} />,
    );
    await screen.findByRole("heading", { name: "钢琴转录结果" });
    const audio = container.querySelector("audio");
    expect(audio).not.toBeNull();

    fireEvent.error(audio!);

    await waitFor(() => expect(mocks.getDownloadUrl).toHaveBeenCalledTimes(2));
    expect(audio).toHaveAttribute("src", "http://api.test/refreshed-source");
  });

  it("records playback only after the player starts successfully", async () => {
    const user = userEvent.setup();
    render(<ResultClient job={job} deleting={false} onDelete={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "播放" }));

    await waitFor(() => expect(mocks.play).toHaveBeenCalled());
    expect(mocks.trackEvent).toHaveBeenCalledWith(job.id, "playback_started", {
      mode: "midi",
    });

    mocks.play.mockResolvedValue(false);
    mocks.trackEvent.mockClear();
    await user.click(screen.getByRole("button", { name: "播放" }));
    await waitFor(() => expect(mocks.play).toHaveBeenCalledTimes(2));
    expect(mocks.trackEvent).not.toHaveBeenCalled();
  });

  it("copies the current high-entropy task URL as a temporary share link", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
    render(<ResultClient job={job} deleting={false} onDelete={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "复制临时分享链接" }));

    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledWith(window.location.href));
    expect(screen.getByRole("button", { name: "已复制分享链接" })).toBeInTheDocument();
  });
});
