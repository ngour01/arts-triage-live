"use client";

import { useState, useEffect, useCallback } from "react";
import AttentionView from "./AttentionView";
import { useTimePeriod } from "@/components/ui/time-period-provider";
import { getVolumeByBucket, type BucketVolume } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorCard } from "@/components/ui/error-card";
import PageLayout from "@/components/layout/PageLayout";

const FALLBACK_VOLUME: BucketVolume[] = [
  { bucket_id: 3, bucket_name: "Product (PSOD)", count: 0 },
  { bucket_id: 4, bucket_name: "Unknown", count: 0 },
];

export default function AttentionPage() {
  const { days } = useTimePeriod();
  const [buckets, setBuckets] = useState<BucketVolume[]>(FALLBACK_VOLUME);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const all = await getVolumeByBucket(days);
      setBuckets(all.filter((b) => b.bucket_id === 3 || b.bucket_id === 4));
      setLastUpdated(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Failed to load data"));
    } finally {
      setIsLoading(false);
    }
  }, [days]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const criticalCount = buckets.reduce((s, b) => s + b.count, 0);

  return (
    <PageLayout
      title="Attention Required"
      subtitle="Product bugs & unclassified failures needing manual review"
      onRefresh={loadData}
      isRefreshing={isLoading}
      lastUpdated={lastUpdated}
      badge={
        <div className="flex items-center gap-1.5 rounded-full bg-rose-100 dark:bg-rose-900/30 px-2.5 py-1 text-rose-700 dark:text-rose-400 text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
          {criticalCount} critical
        </div>
      }
    >
      {isLoading ? (
        <div className="space-y-4">
          <div className="flex gap-4">
            <Skeleton className="h-20 w-48" />
            <Skeleton className="h-20 w-48" />
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <ErrorCard error={error} onRetry={loadData} />
      ) : (
        <AttentionView buckets={buckets} />
      )}
    </PageLayout>
  );
}
