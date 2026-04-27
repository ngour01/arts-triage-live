"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type TimePeriod = "daily" | "weekly" | "monthly";

export interface TimePeriodOption {
  value: TimePeriod;
  label: string;
  days: number;
  description: string;
}

export const TIME_PERIOD_OPTIONS: TimePeriodOption[] = [
  { value: "daily", label: "Daily", days: 7, description: "Last 7 days" },
  { value: "weekly", label: "Weekly", days: 30, description: "Last 30 days" },
  { value: "monthly", label: "Monthly", days: 365, description: "Last 12 months" },
];

const DEFAULT_PERIOD: TimePeriod = "weekly";

function getTimePeriodInfo(period: TimePeriod): TimePeriodOption {
  return TIME_PERIOD_OPTIONS.find((o) => o.value === period) ?? TIME_PERIOD_OPTIONS[1];
}

interface TimePeriodState {
  period: TimePeriod;
  setPeriod: (p: TimePeriod) => void;
  periodInfo: TimePeriodOption;
  days: number;
}

const TimePeriodContext = createContext<TimePeriodState | undefined>(undefined);

function isValidPeriod(v: string): v is TimePeriod {
  return TIME_PERIOD_OPTIONS.some((o) => o.value === v);
}

export function TimePeriodProvider({ children }: { children: React.ReactNode }) {
  const [period, setPeriodState] = useState<TimePeriod>(DEFAULT_PERIOD);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("arts-time-period");
      if (stored && isValidPeriod(stored)) setPeriodState(stored);
    } catch {
      /* ignore */
    }
  }, []);

  const periodInfo = getTimePeriodInfo(period);

  const setPeriod = (p: TimePeriod) => {
    try {
      localStorage.setItem("arts-time-period", p);
    } catch {
      /* ignore */
    }
    setPeriodState(p);
  };

  return (
    <TimePeriodContext.Provider value={{ period, setPeriod, periodInfo, days: periodInfo.days }}>
      {children}
    </TimePeriodContext.Provider>
  );
}

export function useTimePeriod() {
  const ctx = useContext(TimePeriodContext);
  if (!ctx) throw new Error("useTimePeriod must be used within TimePeriodProvider");
  return ctx;
}
