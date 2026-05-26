import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";

export const metadata: Metadata = {
  title: "QuantAgent",
  description: "Quantitative trading platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider>
          {children}
          <ThemeToggle className="fixed bottom-4 right-4 z-[9999] bg-card border border-border rounded-full p-2 shadow-lg" />
        </ThemeProvider>
      </body>
    </html>
  );
}
