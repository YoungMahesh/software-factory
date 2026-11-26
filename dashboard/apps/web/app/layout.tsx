import type { Metadata, Viewport } from "next";
import { DashboardProvider } from "@/components/dashboard-provider";
import { DashboardShell } from "@/components/dashboard-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Modal Sandbox Runner",
  description: "Software Factory Control Plane dashboard for sandboxes, Factory Apps, snapshots, and Scratchpad",
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
        <DashboardProvider>
          <DashboardShell>{children}</DashboardShell>
        </DashboardProvider>
      </body>
    </html>
  );
}
