import type { Metadata } from "next";
import "./globals.css";
import ClientShell from "@/components/ClientShell";

export const metadata: Metadata = {
  title: "ARTs v1.0.0 — Autonomous Relational Triage System",
  description:
    "Management dashboard for CI/CD test failure triage and classification",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans">
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
