"use client";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center px-5 text-center">
      <div className="max-w-md rounded-3xl border border-[#dce3dc] bg-white p-8 shadow-[var(--shadow)]">
        <p className="text-sm font-bold text-[#147d70]">页面没有正常加载</p>
        <h1 className="mt-3 text-3xl font-bold tracking-[-0.04em]">先别反复点，重试一次。</h1>
        <p className="mt-3 text-sm leading-6 text-[#64736f]">如果仍然失败，稍后再打开页面。你的上传不会在此阶段自动开始。</p>
        <button onClick={reset} className="mt-6 rounded-full bg-[#147d70] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#075e55]">
          重新加载
        </button>
      </div>
    </main>
  );
}
