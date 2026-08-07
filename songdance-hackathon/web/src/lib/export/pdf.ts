import { jsPDF } from "jspdf";

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN = 36;
const TITLE_AREA = 34;

export async function createScorePdf(
  title: string,
  scoreContainer: HTMLElement,
): Promise<Uint8Array> {
  const pages = [...scoreContainer.querySelectorAll("svg")];
  if (pages.length === 0) throw new Error("五线谱尚未完成渲染。");
  const pdf = new jsPDF({ unit: "pt", format: "a4", orientation: "portrait", compress: true });
  pdf.setProperties({ title, creator: "SongDance" });

  for (const [index, svg] of pages.entries()) {
    if (index > 0) pdf.addPage("a4", "portrait");
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(15);
    pdf.text(index === 0 ? title : `${title} · ${index + 1}`, MARGIN, MARGIN);
    const source = svgDimensions(svg);
    const availableWidth = PAGE_WIDTH - MARGIN * 2;
    const availableHeight = PAGE_HEIGHT - MARGIN * 2 - TITLE_AREA;
    const scale = Math.min(availableWidth / source.width, availableHeight / source.height);
    const width = source.width * scale;
    const height = source.height * scale;
    const image = await renderSvg(svg, source);
    pdf.addImage(image, "PNG", (PAGE_WIDTH - width) / 2, MARGIN + TITLE_AREA, width, height);
  }
  return new Uint8Array(pdf.output("arraybuffer"));
}

async function renderSvg(
  svg: SVGSVGElement,
  source: { width: number; height: number },
): Promise<string> {
  const serialized = new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob([serialized], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const pixelScale = Math.min(2, 2400 / source.width);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(source.width * pixelScale));
    canvas.height = Math.max(1, Math.round(source.height * pixelScale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("浏览器无法创建 PDF 画布。");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function svgDimensions(svg: SVGSVGElement): { width: number; height: number } {
  const viewBox = svg.getAttribute("viewBox")?.trim().split(/[ ,]+/).map(Number);
  if (viewBox?.length === 4 && viewBox[2] > 0 && viewBox[3] > 0) {
    return { width: viewBox[2], height: viewBox[3] };
  }
  const width = Number.parseFloat(svg.getAttribute("width") ?? "");
  const height = Number.parseFloat(svg.getAttribute("height") ?? "");
  if (width > 0 && height > 0) return { width, height };
  throw new Error("五线谱页面尺寸无效。");
}
