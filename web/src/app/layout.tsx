import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FacturAI — Facturas a Excel con IA",
  description: "Convierte PDFs de facturas a Excel automáticamente con inteligencia artificial. Para autónomos y gastos personales.",
  keywords: ["facturas", "excel", "autónomos", "inteligencia artificial", "PDF"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
