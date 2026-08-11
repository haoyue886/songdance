import Link from "next/link";
import { BrandMark } from "./brand-mark";

export function SiteFooter() {
  return (
    <footer className="bg-[#15332f] text-white">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-5 py-10 sm:px-8 md:flex-row md:items-end md:justify-between lg:px-10">
        <div>
          <BrandMark />
          <p className="mt-4 max-w-md text-sm leading-6 text-[#bed0ca]">
            匿名 MVP。音频不用于模型训练，任务页提供立即删除入口。
          </p>
        </div>
        <div className="flex flex-wrap gap-5 text-sm font-semibold text-[#d9e5e1]">
          <Link href="/audio-to-midi">Audio to MIDI</Link>
          <Link href="/privacy">隐私说明</Link>
          <Link href="/terms">使用条款</Link>
          <Link href="/examples">转录示例</Link>
          <Link href="#how-it-works">处理流程</Link>
        </div>
      </div>
    </footer>
  );
}
