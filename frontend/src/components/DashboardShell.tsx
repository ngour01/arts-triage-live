"use client";

import { useState } from "react";
import { Card, DonutChart, Title, Text } from "@tremor/react";
import MetricsBar from "./MetricsBar";
import FailureVolumeChart from "./FailureVolumeChart";
import TriageProgressChart from "./TriageProgressChart";
import BucketCards from "./BucketCards";
import FailuresTable, { type FailureRow } from "./FailuresTable";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/ui/error-card";
import PageLayout from "@/components/layout/PageLayout";
import { useTimePeriod } from "@/components/ui/time-period-provider";
import {
  patchSignalBug,
  type Summary,
  type BucketVolume,
  type TriageProgressDay,
  type ExportData,
  type ExportPattern,
} from "@/lib/api";

const BUCKET_NAMES: Record<number, string> = {
  1: "User Errors",
  2: "Infra Errors",
  3: "Product (PSOD)",
  4: "Unknown",
  5: "Test Logic",
  6: "Timeouts",
};

const DONUT_COLORS = ["amber", "cyan", "rose", "slate", "violet", "orange"];
const LEGEND_BG_COLORS = [
  "bg-amber-500",
  "bg-cyan-500",
  "bg-rose-500",
  "bg-slate-500",
  "bg-violet-500",
  "bg-orange-500",
];

interface Props {
  summary: Summary;
  volumeData: BucketVolume[];
  progressData: TriageProgressDay[];
  exportData: ExportData | null;
  isLoading?: boolean;
  error?: Error | null;
  onRefresh?: () => void;
  lastUpdated?: string | null;
}

function KPICardsSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {[1, 2, 3, 4].map((i) => (
        <Card key={i} className="p-6">
          <div className="flex items-start justify-between">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
          <div className="mt-4 space-y-2">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="mt-4 h-12 w-full" />
        </Card>
      ))}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <Card className="p-6">
      <div className="space-y-2 mb-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-48" />
      </div>
      <Skeleton className="h-64 w-full" />
    </Card>
  );
}

function TableSkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="px-6 py-4 border-b border-border flex justify-between">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <div className="p-6 space-y-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </Card>
  );
}

function BucketCardsSkeleton() {
  return (
    <div>
      <Skeleton className="h-4 w-40 mb-3" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Card key={i} className="p-4">
            <Skeleton className="h-9 w-9 rounded-lg mb-3" />
            <Skeleton className="h-3 w-16 mb-2" />
            <Skeleton className="h-7 w-10" />
          </Card>
        ))}
      </div>
    </div>
  );
}

function FullWidthChartSkeleton() {
  return (
    <Card className="p-6">
      <div className="space-y-2 mb-4">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="h-72 w-full" />
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <KPICardsSkeleton />
      <BucketCardsSkeleton />
      <FullWidthChartSkeleton />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>
      <TableSkeleton />
    </div>
  );
}

function buildRows(
  exportData: ExportData | null,
  bucketId: number
): FailureRow[] {
  if (!exportData) return [];
  const patternMap = new Map<string, ExportPattern>();
  exportData.patterns.forEach((p) => patternMap.set(p.fingerprint, p));
  return exportData.failures
    .filter((f) => f.latest_bucket_id === bucketId && f.is_latest === 1)
    .map((f) => {
      const pattern = patternMap.get(f.fingerprint);
      return {
        testCase: f.test_case_name,
        feature: f.feature_name,
        message:
          pattern?.scrubbed_pattern ??
          (f as { scrubbed_message?: string }).scrubbed_message ??
          "Unknown Error",
        bugId: f.bug_id,
        logUrl: f.log_url,
        isSticky: f.has_sticky_failure,
        isPassing: f.is_currently_passing,
        attemptId: f.attempt_id,
        fingerprint: f.fingerprint,
      };
    });
}

export default function DashboardShell({
  summary,
  volumeData,
  progressData,
  exportData,
  isLoading = false,
  error = null,
  onRefresh,
  lastUpdated,
}: Props) {
  const [selectedBucket, setSelectedBucket] = useState<number>(3);
  const { periodInfo } = useTimePeriod();

  const rows = buildRows(exportData, selectedBucket);

  const handleBugSave = async (
    attemptId: number,
    fingerprint: string,
    bugId: string | null
  ) => {
    await patchSignalBug({
      test_attempt_id: attemptId,
      fingerprint,
      bug_id: bugId,
    });
    onRefresh?.();
  };
  const bucketLabel = BUCKET_NAMES[selectedBucket] ?? "Unknown";

  const totalInBuckets = volumeData.reduce((s, d) => s + d.count, 0);
  const donutData = volumeData.map((d) => ({
    name: d.bucket_name,
    value: d.count,
  }));

  return (
    <PageLayout
      title="Overview"
      subtitle={`CI/CD failure analytics — ${periodInfo.description}`}
      isRefreshing={isLoading}
      onRefresh={onRefresh}
      lastUpdated={lastUpdated}
    >
      {isLoading && !totalInBuckets ? (
        <DashboardSkeleton />
      ) : error ? (
        <ErrorCard error={error} onRetry={onRefresh} />
      ) : (
        <div className="space-y-6">
          {/* Row 1: KPI Summary */}
          <MetricsBar
            totalFailures={summary.total_failures}
            autoTriagedPct={summary.auto_triaged_pct}
            activeProductBugs={summary.active_product_bugs}
            trends={summary.trends}
            progressData={progressData}
          />

          {/* Row 2: Classification Buckets (interactive selector) */}
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-3">
              Classification Buckets
            </h3>
            <BucketCards
              data={volumeData}
              selectedBucket={selectedBucket}
              onSelect={setSelectedBucket}
            />
          </div>

          {/* Row 3: Triage Progress (full width, prominence for effectiveness trend) */}
          <TriageProgressChart data={progressData} />

          {/* Row 4: Distribution charts (donut + bar, 2-col) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="p-6">
              <div className="mb-4">
                <Title className="text-lg font-semibold">Bucket Distribution</Title>
                <Text className="text-sm text-muted-foreground">
                  Failure classification breakdown
                </Text>
              </div>
              <div className="flex flex-col items-center">
                <DonutChart
                  data={donutData}
                  index="name"
                  category="value"
                  colors={DONUT_COLORS}
                  className="h-40 w-40"
                  showAnimation
                  showTooltip
                  variant="donut"
                  valueFormatter={(v) => v.toLocaleString()}
                />
                <div className="mt-6 w-full space-y-2">
                  {volumeData.map((d, i) => (
                    <div key={d.bucket_id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`h-3 w-3 rounded-full ${LEGEND_BG_COLORS[i] || "bg-gray-500"}`} />
                        <span className="text-sm font-medium text-foreground truncate">
                          {d.bucket_name}
                        </span>
                      </div>
                      <span className="text-sm font-semibold text-foreground">
                        {d.count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              {totalInBuckets > 0 && (
                <div className="mt-6 pt-4 border-t border-border">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Total failures</span>
                    <span className="font-semibold text-foreground">
                      {totalInBuckets.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>

            <FailureVolumeChart data={volumeData} />
          </div>

          {/* Row 5: Detail table (driven by bucket selection) */}
          <FailuresTable
            rows={rows}
            title={`${bucketLabel} Details`}
            onBugIdSave={handleBugSave}
          />
        </div>
      )}
    </PageLayout>
  );
}
