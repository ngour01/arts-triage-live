"use client";

import ThemeProvider from "./ThemeProvider";
import Sidebar from "./Sidebar";
import { TimePeriodProvider } from "@/components/ui/time-period-provider";

export default function ClientShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ThemeProvider>
      <TimePeriodProvider>
        <div className="flex min-h-screen">
          <aside className="hidden md:flex md:w-56 md:flex-col md:fixed md:inset-y-0 border-r bg-background z-50">
            <Sidebar />
          </aside>
          <div className="flex-1 md:ml-56 transition-all duration-300">
            {children}
          </div>
        </div>
      </TimePeriodProvider>
    </ThemeProvider>
  );
}
