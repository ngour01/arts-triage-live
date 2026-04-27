"use client";

import { Card, BarChart, Title, Text } from "@tremor/react";
import type { BucketVolume } from "@/lib/api";

interface Props {
  data: BucketVolume[];
}

function valueFormatter(value: number): string {
  return value.toLocaleString();
}

export default function FailureVolumeChart({ data }: Props) {
  const chartData = data.map((d) => ({
    name: d.bucket_name,
    Failures: d.count,
  }));

  return (
    <Card className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <div>
          <Title className="text-lg font-semibold">Failure Volume by Bucket</Title>
          <Text className="text-sm text-muted-foreground">
            Distribution across classification categories
          </Text>
        </div>
      </div>
      <BarChart
        data={chartData}
        index="name"
        categories={["Failures"]}
        colors={["blue"]}
        yAxisWidth={36}
        className="h-64"
        showAnimation
        showGridLines
        valueFormatter={valueFormatter}
        customTooltip={({ payload, active, label }) => {
          if (!active || !payload || payload.length === 0) return null;
          return (
            <div className="rounded-lg border bg-background p-3 shadow-lg min-w-[140px]">
              <p className="text-sm font-medium text-foreground mb-2 border-b pb-2">
                {label}
              </p>
              {payload.map((item: any, idx: number) => (
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
          );
        }}
      />
    </Card>
  );
}
