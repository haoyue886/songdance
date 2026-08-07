"use client";

import Link from "next/link";

type RightsConfirmationProps = {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
};

export function RightsConfirmation({ checked, disabled, onChange }: RightsConfirmationProps) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-[#dce4de] bg-[#f7f9f5] p-4 text-sm leading-6 text-[#52635f]">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.checked)}
        className="mt-1 size-4 accent-[#147d70]"
      />
      <span>
        我确认自己拥有处理和转录该音频所需的版权、许可或其他合法权利。
        上传内容不会用于训练模型；任务创建后可在任务页立即删除。提交即表示你已阅读
        <Link className="font-bold text-[#075e55] underline underline-offset-2" href="/privacy">
          隐私说明
        </Link>
        和
        <Link className="font-bold text-[#075e55] underline underline-offset-2" href="/terms">
          使用条款
        </Link>
        。
      </span>
    </label>
  );
}
