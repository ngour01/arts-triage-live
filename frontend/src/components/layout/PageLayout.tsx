"use client";

import { Header } from "./Header";

interface PageLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  lastUpdated?: string | null;
  badge?: React.ReactNode;
}

export function PageLayout({
  title,
  subtitle,
  children,
  isRefreshing = false,
  onRefresh,
  lastUpdated,
  badge,
}: PageLayoutProps) {
  return (
    <div className="min-h-screen">
      <Header
        title={title}
        subtitle={subtitle}
        isRefreshing={isRefreshing}
        onRefresh={onRefresh}
        lastUpdated={lastUpdated}
        badge={badge}
      />

      <main className="p-4 md:p-6 lg:p-8">{children}</main>

      <footer className="mt-8 px-4 md:px-6 lg:px-8 pb-6">
        <div className="pt-6 border-t border-border">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-muted-foreground">
            <p>ARTs v1.0.0 &mdash; Autonomous Relational Triage System</p>
            <div className="flex items-center gap-4">
              <span>Version 1.0.0</span>
              {lastUpdated && (
                <span>
                  Last updated:{" "}
                  {new Date(lastUpdated).toLocaleString("en-US", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </span>
              )}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default PageLayout;
