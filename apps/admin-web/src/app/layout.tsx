import type { Metadata } from "next";
import type React from "react";
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/manrope/800.css";
import "material-symbols/outlined.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inventory admin",
  description: "Tenant dashboard for inventory platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head />
      <body
        className="min-h-screen bg-background font-sans text-on-surface antialiased"
        style={{ "--font-body": "'Public Sans', system-ui, sans-serif", "--font-display": "'Manrope', system-ui, sans-serif" } as React.CSSProperties}
      >
        {children}
      </body>
    </html>
  );
}
