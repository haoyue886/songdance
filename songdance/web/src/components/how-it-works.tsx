const STEPS = [
  ["选择片段", "上传钢琴录音，在波形上截取 1–90 秒。"],
  ["AI 转录", "系统生成 MIDI，再完成基础节拍、分手与乐谱结构化。"],
  ["试听导出", "对照五线谱和钢琴卷帘，下载 MIDI、MusicXML 或 PDF。"],
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto w-full max-w-7xl px-5 py-24 sm:px-8 lg:px-10">
      <div className="grid gap-14 lg:grid-cols-[0.7fr_1.3fr]">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">Three honest steps</p>
          <h2 className="mt-4 font-display text-4xl leading-tight tracking-[-0.035em] sm:text-5xl">
            从声音，到能继续工作的音符。
          </h2>
          <p className="mt-5 max-w-md leading-7 text-[#61716c]">
            首版只解决钢琴转录。它不会假装每次都完美；低质量输入会给出明确失败原因，而不是伪造准确结果。
          </p>
        </div>
        <ol className="divide-y divide-[#cad7d1] border-y border-[#cad7d1]">
          {STEPS.map(([title, body], index) => (
            <li key={title} className="grid grid-cols-[2.6rem_1fr] gap-4 py-7 sm:grid-cols-[3.5rem_12rem_1fr] sm:items-center">
              <span className="font-display text-2xl italic text-[#77aa9e]">0{index + 1}</span>
              <h3 className="text-lg font-bold">{title}</h3>
              <p className="col-start-2 text-sm leading-6 text-[#65736f] sm:col-start-auto">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
