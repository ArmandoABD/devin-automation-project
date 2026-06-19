import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Devin Remediation Control",
  description: "Event-driven autonomous remediation, powered by Devin",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
