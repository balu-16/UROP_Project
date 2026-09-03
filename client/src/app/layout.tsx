import type { Metadata } from "next";
import { Inter, Sora } from "next/font/google";
import { MotionConfig } from "framer-motion";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RAGnostic — Adaptive Retrieval-Augmented AI",
  description:
    "A research-ready chatbot with adaptive retrieval, graph expansion, threshold-based depth selection, and structured streaming answers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${sora.variable} font-sans antialiased`}
      >
        <TooltipProvider delayDuration={300}>
          <MotionConfig reducedMotion="user">
            <ToastProvider>{children}</ToastProvider>
          </MotionConfig>
        </TooltipProvider>
      </body>
    </html>
  );
}
