"use client";

import { useState } from "react";
import { Menu, RefreshCw, Wifi, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { TimePeriodSelect } from "@/components/ui/time-period-select";
import { useTheme } from "@/components/ThemeProvider";
import Sidebar from "@/components/Sidebar";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title?: string;
  subtitle?: string;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  lastUpdated?: string | null;
  badge?: React.ReactNode;
}

export function Header({
  title = "Dashboard",
  subtitle,
  isRefreshing = false,
  onRefresh,
  lastUpdated,
  badge,
}: HeaderProps) {
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const { theme, toggle } = useTheme();

  const formattedTime = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      })
    : null;

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-16 items-center gap-4 px-4 md:px-6">
        <Sheet open={isSheetOpen} onOpenChange={setIsSheetOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 p-0">
            <SheetHeader className="sr-only">
              <SheetTitle>Navigation Menu</SheetTitle>
            </SheetHeader>
            <Sidebar />
          </SheetContent>
        </Sheet>

        <div className="flex-1">
          <h1 className="text-lg font-semibold md:text-xl">{title}</h1>
          {subtitle && (
            <p className="text-xs text-muted-foreground hidden sm:block">
              {subtitle}
            </p>
          )}
          {!subtitle && formattedTime && (
            <p className="text-xs text-muted-foreground hidden sm:block">
              Last updated: {formattedTime}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {badge}

          <div
            className="flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 px-2.5 py-1 text-emerald-700 dark:text-emerald-400 text-xs font-medium"
          >
            <Wifi className="h-3 w-3" />
            <span className="hidden sm:inline">Live</span>
          </div>

          {onRefresh && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-label="Refresh data"
            >
              <RefreshCw
                className={cn("h-4 w-4", isRefreshing && "animate-spin")}
              />
            </Button>
          )}

          <div className="hidden sm:block">
            <TimePeriodSelect compact />
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={toggle}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </header>
  );
}

export default Header;
