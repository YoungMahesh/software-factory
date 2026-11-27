import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dashboard Deployer",
  description: "Standalone deployment console for Sandbox Web Dashboard (GitHub main to App Base Domain)",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full bg-canvas text-ink">
      <body className="min-h-full font-sans antialiased bg-canvas text-ink selection:bg-primary selection:text-on-primary">
        {children}
      </body>
    </html>
  );
}
