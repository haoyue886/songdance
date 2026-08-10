import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SongDance — Piano audio to editable MIDI",
  description:
    "Turn a piano recording into MIDI, MusicXML and readable sheet music.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
