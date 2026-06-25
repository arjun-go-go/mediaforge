import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { RouteGuard } from "@/components/RouteGuard";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "MediaForge",
  description: "AI 媒体生成工作台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${inter.className} font-sans antialiased`}>
        <RouteGuard>{children}</RouteGuard>
      </body>
    </html>
  );
}
