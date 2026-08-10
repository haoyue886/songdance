type BrandMarkProps = {
  compact?: boolean;
};

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <span className="inline-flex items-center gap-2.5" aria-label="SongDance">
      <span className="grid size-9 place-items-center rounded-xl bg-[#147d70] text-white shadow-[0_8px_22px_rgba(20,125,112,0.22)]">
        <svg
          aria-hidden="true"
          viewBox="0 0 32 32"
          className="size-5"
          fill="none"
        >
          <path
            d="M11 7v13.25a4.25 4.25 0 1 1-2-3.61V10l13-3v10.25a4.25 4.25 0 1 1-2-3.61V4.5L11 7Z"
            fill="currentColor"
          />
        </svg>
      </span>
      {!compact && (
        <span className="text-[1.05rem] font-bold tracking-[-0.025em]">
          SongDance
        </span>
      )}
    </span>
  );
}
