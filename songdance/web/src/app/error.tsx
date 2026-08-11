"use client";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center px-5 text-center">
      <div className="max-w-md rounded-lg border border-[#dce3dc] bg-white p-8 shadow-[var(--shadow)]">
        <p className="text-sm font-bold text-[#147d70]">The page did not load correctly</p>
        <h1 className="mt-3 text-3xl font-bold">Try loading it once more.</h1>
        <p className="mt-3 text-sm leading-6 text-[#64736f]">If it still fails, return later. No upload starts automatically from this screen.</p>
        <button onClick={reset} className="mt-6 rounded-full bg-[#147d70] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#075e55]">
          Reload
        </button>
      </div>
    </main>
  );
}
