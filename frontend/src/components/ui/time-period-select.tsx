"use client";

import { Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useTimePeriod,
  TIME_PERIOD_OPTIONS,
} from "@/components/ui/time-period-provider";
import { cn } from "@/lib/utils";

interface TimePeriodSelectProps {
  className?: string;
  compact?: boolean;
}

export function TimePeriodSelect({ className, compact = false }: TimePeriodSelectProps) {
  const { period, setPeriod } = useTimePeriod();

  return (
    <div className={cn("flex items-center rounded-lg border bg-muted p-1", className)}>
      {TIME_PERIOD_OPTIONS.map((option) => (
        <Button
          key={option.value}
          variant={period === option.value ? "default" : "ghost"}
          size="sm"
          onClick={() => setPeriod(option.value)}
          className={cn(
            "transition-all",
            compact ? "h-6 px-2 text-xs" : "h-7 px-3 text-xs"
          )}
          title={option.description}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

export function TimePeriodIndicator({ className }: { className?: string }) {
  const { periodInfo } = useTimePeriod();

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground",
        className
      )}
    >
      <Calendar className="h-3 w-3" />
      <span>{periodInfo.label}</span>
    </div>
  );
}
