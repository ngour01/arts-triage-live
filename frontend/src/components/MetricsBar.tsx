"use client";

import { useMemo } from "react";
import { Card, SparkAreaChart } from "@tremor/react";
import {
  AlertTriangle,
  CheckCircle2,
  Bug,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TrendData, TriageProgressDay } from "@/lib/api";

interface MetricsBarProps {
  totalFailures: number;
  autoTriagedPct: number;
  activeProductBugs: number;
  trends?: TrendData;
  progressData?: TriageProgressDay[];
}

function TrendIndicator({ trend }: { trend: number }) {
  const normalized = Object.is(trend, -0) ? 0 : trend;
  const abs = Math.abs(normalized);
  const direction = normalized > 0 ? "up" : normalized < 0 ? "down" : "neutral";

  const Icon = direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;

  const colorClass =
    direction === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : direction === "down"
      ? "text-red-600 dark:text-red-400"
      : "text-muted-foreground";

  const bgClass =
    direction === "up"
      ? "bg-emerald-100 dark:bg-emerald-900/30"
      : direction === "down"
      ? "bg-red-100 dark:bg-red-900/30"
      : "bg-muted";

  const display =
    direction === "up" ? `+${abs}%` : direction === "down" ? `-${abs}%` : `${abs}%`;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        colorClass,
        bgClass
      )}
    >
      <Icon className="h-3 w-3" />
      <span>{display}</span>
    </div>
  );
}

export default function MetricsBar({
  totalFailures,
  autoTriagedPct,
  activeProductBugs,
  trends,
  progressData,
}: MetricsBarProps) {
  const triaged = Math.round((totalFailures * autoTriagedPct) / 100);
  const triageRate = totalFailures > 0
    ? Math.round((triaged / totalFailures) * 100)
    : 0;

  const sparkData = useMemo(() => {
    if (!progressData || progressData.length === 0) return [];
    return progressData.map((d, i) => ({
      index: i,
      value: d.triaged + d.untriaged,
    }));
  }, [progressData]);

  const metrics = [
    {
      label: "Total Failures",
      value: totalFailures.toLocaleString(),
      icon: AlertTriangle,
      colorClass: "bg-blue-500",
      sparkColor: "blue" as const,
      trend: trends?.total_failures_trend,
    },
    {
      label: "Auto-Triaged",
      value: `${autoTriagedPct}%`,
      sub: `${triaged} of ${totalFailures}`,
      icon: CheckCircle2,
      colorClass: "bg-emerald-500",
      sparkColor: "emerald" as const,
      trend: trends?.auto_triaged_trend,
    },
    {
      label: "Active Product Bugs",
      value: activeProductBugs.toLocaleString(),
      icon: Bug,
      colorClass: "bg-amber-500",
      sparkColor: "amber" as const,
      trend: trends?.product_bugs_trend,
    },
    {
      label: "Triage Rate",
      value: totalFailures > 0 ? `${triageRate}%` : "N/A",
      sub: "Classification hit rate",
      icon: TrendingUp,
      colorClass: "bg-violet-500",
      sparkColor: "violet" as const,
      trend: undefined,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {metrics.map((m) => {
        const Icon = m.icon;
        return (
          <Card key={m.label} className="relative overflow-hidden">
            <div className="flex items-start justify-between">
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg",
                  m.colorClass
                )}
              >
                <Icon className="h-5 w-5 text-white" />
              </div>
              {m.trend !== undefined && <TrendIndicator trend={m.trend} />}
            </div>
            <div className="mt-4">
              <p className="text-3xl font-bold tracking-tight text-foreground">
                {m.value}
              </p>
              <p className="text-sm font-medium text-muted-foreground mt-1">
                {m.label}
              </p>
              {m.sub && (
                <p className="text-xs text-muted-foreground mt-0.5">{m.sub}</p>
              )}
            </div>
            {sparkData.length > 0 && (
              <div className="mt-4 h-12">
                <SparkAreaChart
                  data={sparkData}
                  categories={["value"]}
                  index="index"
                  colors={[m.sparkColor]}
                  className="h-full w-full"
                  curveType="monotone"
                  noDataText=""
                />
              </div>
            )}
            <div
              className={cn(
                "absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-10 blur-2xl",
                m.colorClass
              )}
            />
          </Card>
        );
      })}
    </div>
  );
}
