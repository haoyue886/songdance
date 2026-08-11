import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "隐私说明",
  description: "SongDance 音频处理、保存期限和匿名事件说明。",
  alternates: { canonical: "/privacy" },
  openGraph: {
    type: "website",
    url: "/privacy",
    title: "SongDance 隐私说明",
    description: "了解 SongDance 如何处理、临时保存和删除上传音频。",
  },
  twitter: {
    card: "summary",
    title: "SongDance 隐私说明",
    description: "了解 SongDance 如何处理、临时保存和删除上传音频。",
  },
};

const SECTIONS = [
  {
    heading: "处理的数据",
    paragraphs: [
      "我们接收你主动提交的最长 90 秒钢琴音频片段，并生成 MIDI、MusicXML、时间轴和乐谱预览。任务使用随机高熵链接，不要求账户。",
      "音频和转录产物仅用于完成当前任务，不用于训练模型，也不会作为公开示例发布。",
    ],
  },
  {
    heading: "保存与删除",
    paragraphs: [
      "源音频、处理中间文件和导出产物在任务创建 24 小时后自动删除。任务页提供立即删除；删除成功后原任务链接不可恢复。",
      "下载链接只有短期签名有效期。对象存储保持私有，浏览器不会获得永久公开对象地址。",
    ],
  },
  {
    heading: "日志与事件",
    paragraphs: [
      "服务记录请求 ID、任务 ID 的不可逆摘要、处理阶段耗时、模型版本和错误码，用于排障和判断功能是否可用。",
      "日志和产品事件不包含音频内容、原始文件名、完整对象键或敏感来源 URL。匿名限流会短期使用 IP 的加密摘要控制滥用。",
    ],
  },
  {
    heading: "你的控制权",
    paragraphs: [
      "不要上传没有处理权利的内容。任务仍有效时，你可以在任务页下载产物或立即删除全部任务数据。",
      "SongDance 当前是匿名 MVP，不建立用户画像，也没有广告追踪或跨站身份关联。",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Privacy"
      title="你的音频只为这次转录而处理"
      summary="这份说明讲清楚我们接收什么、保存多久、记录哪些运行信息，以及你如何立即删除。"
      sections={SECTIONS}
    />
  );
}
