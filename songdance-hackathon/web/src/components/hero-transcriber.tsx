const PRODUCT_LIMITS = ["仅支持钢琴", "最长 90 秒", "支持立即删除"];

export function HeroTranscriber() {
  return (
    <section className="mx-auto grid w-full max-w-7xl grid-cols-[minmax(0,1fr)] overflow-x-clip px-5 pb-24 pt-14 sm:px-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:items-center lg:gap-12 lg:px-10 lg:pt-20">
      <div className="min-w-0 max-w-2xl">
        <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#c9dfd7] bg-white/65 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-[#147d70]">
          <span className="size-1.5 rounded-full bg-[#147d70]" />
          AI Piano Transcriber
        </p>
        <h1 className="font-display text-[clamp(2.25rem,10vw,6.4rem)] leading-[0.98] tracking-[-0.055em] text-[#15332f] [word-break:break-all]">
          让钢琴录音
          <span className="block italic text-[#147d70]">重新变得可编辑</span>
        </h1>
        <p className="mt-7 max-w-xl text-lg leading-8 text-[#53645f] [word-break:break-all] sm:text-xl">
          上传一段钢琴音频，获得可导入 DAW 的 MIDI、MusicXML
          和清晰五线谱。先听结果，再决定如何继续制作。
        </p>
        <div className="mt-8 flex flex-wrap gap-2.5" aria-label="产品限制">
          {PRODUCT_LIMITS.map((limit) => (
            <span
              key={limit}
              className="rounded-full bg-[#e5eee9] px-3 py-1.5 text-sm font-semibold text-[#48605a]"
            >
              {limit}
            </span>
          ))}
        </div>
      </div>

      <div className="relative mt-12 min-w-0 lg:mt-0">
        <div className="absolute -inset-4 -z-10 rounded-[2.4rem] bg-[#dcefe7]/70 blur-2xl" />
        <div className="min-w-0 overflow-hidden rounded-[2rem] border border-white/85 bg-white p-3 shadow-[var(--shadow)] sm:p-5">
          <div className="min-w-0 overflow-hidden rounded-[1.45rem] border border-dashed border-[#a9c9bf] bg-[#fbfcf8] px-4 py-14 text-center sm:px-10 sm:py-16">
            <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-[#dff0e9] text-[#147d70]">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-7" fill="none">
                <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M5 14v3.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </span>
            <h2 className="mt-5 max-w-full text-lg font-bold tracking-[-0.02em] [word-break:break-all] sm:text-xl">上传并截取钢琴音频</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#6a7975] [word-break:break-all]">
              支持 MP3、WAV 和 M4A；选择 1–90 秒片段后，提交为可刷新恢复的匿名任务。
            </p>
            <a
              href="/transcribe"
              className="mt-6 inline-flex min-h-11 items-center justify-center rounded-full bg-[#147d70] px-5 text-sm font-bold text-white transition hover:bg-[#075e55]"
            >
              开始上传与截取
            </a>
            <a href="/examples"
              className="ml-3 mt-6 inline-flex min-h-11 items-center justify-center rounded-full border border-[#b9cdc6] px-5 text-sm font-bold text-[#075e55] transition hover:border-[#147d70]">
              查看真实示例
            </a>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {["MIDI", "MusicXML", "PDF 乐谱"].map((format) => (
              <div key={format} className="rounded-xl bg-[#f2f5f1] px-3 py-3 text-center text-xs font-bold text-[#57706a]">
                {format}
              </div>
            ))}
          </div>
          <p className="px-2 pb-1 pt-4 text-center text-xs leading-5 text-[#6a7975]">
            上传前必须确认你拥有处理该音频所需的版权或授权。
          </p>
        </div>
      </div>
    </section>
  );
}
