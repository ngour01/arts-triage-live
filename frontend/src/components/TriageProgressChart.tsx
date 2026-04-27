"use client";

import { useState } from "react";
import { Card, AreaChart, Title, Text } from "@tremor/react";
import { MultiSelect } from "@/components/ui/multi-select";
import type { TriageProgressDay } from "@/lib/api";

interface Props {
  data: TriageProgressDay[];
}

const SERIES_OPTIONS = [
  { value: "Triaged", label: "Triaged", color: "#10b981" },
  { value: "Un-triaged", label: "Un-triaged", color: "#f43f5e" },
];

const SERIES_COLORS: Record<string, string> = {
  Triaged: "emerald",
  "Un-triaged": "rose",
};

function valueFormatter(value: number): string {
  return value.toLocaleString();
}

export default function TriageProgressChart({ data }: Props) {
  const [selectedSeries, setSelectedSeries] = useState<string[]>(["Triaged", "Un-triaged"]);

  const chartData = data.map((d) => ({
    date: d.date,
    Triaged: d.triaged,
    "Un-triaged": d.untriaged,
  }));

  const activeCategories = selectedSeries.length > 0 ? selectedSeries : ["Triaged", "Un-triaged"];
  const activeColors = activeCategories.map((c) => SERIES_COLORS[c] || "gray");

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Title className="text-lg font-semibold">Triage Progress</Title>
          <Text className="text-sm text-muted-foreground">
            Classification trend over the selected period
          </Text>
        </div>
        <MultiSelect
          options={SERIES_OPTIONS}
          selected={selectedSeries}
          onChange={setSelectedSeries}
          placeholder="Series"
        />
      </div>
      <AreaChart
        data={chartData}
        index="date"
        categories={activeCategories}
        colors={activeColors}
        yAxisWidth={36}
        className="h-72"
        showAnimation
        curveType="monotone"
        showGridLines
        showLegend
        valueFormatter={valueFormatter}
        customTooltip={({ payload, active, label }) => {
          if (!active || !payload || payload.length === 0) return null;
          const sorted = [...payload].sort(
            (a: any, b: any) => (b.value as number) - (a.value as number)
          );
          return (
            <div className="rounded-lg border bg-background p-3 shadow-lg min-w-[160px]">
              <p className="text-sm font-medium text-foreground mb-2 border-b pb-2">
                {label}
              </p>
              <div className="space-y-1">
                {sorted.map((item: any, idx: number) => (
                  <div key={idx} className="flex items-center justify-between gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <div
                        className="h-2.5 w-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-muted-foreground text-xs">{item.dataKey}</span>
                    </div>
                    <span className="font-medium text-foreground">
                      {valueFormatter(item.value as number)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        }}
      />
    </Card>
  );
}
