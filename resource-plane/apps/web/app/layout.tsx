import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Base Template - Modern Full-Stack App",
  description: "Bare-minimum modern full-stack web and mobile template",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-canvas text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
