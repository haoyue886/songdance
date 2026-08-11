import Link from "next/link";
import { BrandMark } from "./brand-mark";

const NAV_ITEMS = [
  { href: "/#features", label: "功能" },
  { href: "/#how-it-works", label: "工作原理" },
  { href: "/audio-to-midi", label: "Audio to MIDI" },
  { href: "/examples", label: "示例" },
  { href: "/privacy", label: "隐私" },
];

export function SiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-5 py-5 sm:px-8 lg:px-10">
      <Link href="/" aria-label="返回 SongDance 首页">
        <BrandMark />
      </Link>
      <nav aria-label="主导航" className="hidden items-center gap-7 md:flex">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="text-sm font-semibold text-[#52635f] transition-colors hover:text-[#075e55]"
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <Link
        href="/#how-it-works"
        className="inline-flex rounded-full border border-[#c8d8d2] bg-white/75 px-3 py-2 text-xs font-bold text-[#075e55] transition hover:border-[#147d70] hover:bg-white sm:px-4 sm:text-sm"
      >
        查看流程
      </Link>
    </header>
  );
}
