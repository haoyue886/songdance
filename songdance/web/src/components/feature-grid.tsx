const FEATURES = [
  {
    number: "01",
    title: "保留可编辑数据",
    body: "不是把音频包装成图片，而是生成能继续进 DAW 或记谱软件的 MIDI 与 MusicXML。",
  },
  {
    number: "02",
    title: "先验证，再下载",
    body: "用五线谱和钢琴卷帘对照原音，快速判断结果值不值得继续修。",
  },
  {
    number: "03",
    title: "临时处理，不做曲库",
    body: "自动清理功能接通后，上传音频和产物将最长保存 24 小时；当前任务支持立即删除。",
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className="border-y border-[#d9e0da] bg-[#fffdf8]">
      <div className="mx-auto w-full max-w-7xl px-5 py-20 sm:px-8 lg:px-10">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#147d70]">What matters</p>
        <div className="mt-5 grid gap-5 md:grid-cols-3">
          {FEATURES.map((feature) => (
            <article key={feature.number} className="rounded-3xl border border-[#e1e6e1] bg-white p-7">
              <span className="font-display text-3xl italic text-[#86b7ab]">{feature.number}</span>
              <h2 className="mt-10 text-xl font-bold tracking-[-0.025em]">{feature.title}</h2>
              <p className="mt-3 text-[0.95rem] leading-7 text-[#65736f]">{feature.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
