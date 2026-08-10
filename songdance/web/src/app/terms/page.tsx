import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "使用条款 - SongDance",
  description: "SongDance 内容权利、服务限制和合理使用说明。",
};

const SECTIONS = [
  {
    heading: "内容权利",
    paragraphs: [
      "你必须拥有上传、处理和转录音频所需的版权、许可或其他合法权利。不得提交私密泄露内容、侵权内容或法律禁止处理的内容。",
      "你保留对原音频的权利。使用 SongDance 不会把音频或音乐作品的所有权转让给我们。",
    ],
  },
  {
    heading: "服务边界",
    paragraphs: [
      "首版只面向最长 90 秒的钢琴音频。自动转录可能包含错音、漏音、节拍或谱面错误；关键制作或出版用途应由你复核。",
      "服务不承诺持续可用。容量、匿名频率和每日任务数会受限，维护或依赖故障时可能暂时停止接受任务。",
    ],
  },
  {
    heading: "合理使用",
    paragraphs: [
      "不得绕过限流、批量消耗推理资源、探测其他任务链接、攻击服务或利用产物传播恶意内容。",
      "每个 IP 默认每小时最多创建 3 个任务，同时最多运行 1 个任务。达到容量时请按页面提示稍后重试。",
    ],
  },
  {
    heading: "删除与中断",
    paragraphs: [
      "任务和产物默认在 24 小时后删除。你也可以立即删除；删除不可撤销，因此请先保存需要的导出文件。",
      "对明显滥用、违法请求或威胁系统安全的流量，服务可以拒绝处理并清理相关临时数据。",
    ],
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Terms"
      title="只处理你有权处理的内容"
      summary="SongDance 是受限的自动转录工具，不是准确性担保，也不是绕过内容权利或平台限制的通道。"
      sections={SECTIONS}
    />
  );
}
