"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import DashboardShell from "@/components/DashboardShell";
import { useTimePeriod } from "@/components/ui/time-period-provider";
import { Button } from "@/components/ui/button";
import {
  getSummary,
  getVolumeByBucket,
  getTriageProgress,
  listRuns,
  getExportDataAll,
  triageLogUrl,
  triageDiscover,
  type Summary,
  type BucketVolume,
  type TriageProgressDay,
  type ExportData,
  type RunRow,
} from "@/lib/api";

const FALLBACK_SUMMARY: Summary = {
  total_failures: 0,
  auto_triaged_pct: 0,
  active_product_bugs: 0,
};

const FALLBACK_VOLUME: BucketVolume[] = [
  { bucket_id: 1, bucket_name: "User Errors", count: 0 },
  { bucket_id: 2, bucket_name: "Infra Errors", count: 0 },
  { bucket_id: 3, bucket_name: "Product (PSOD)", count: 0 },
  { bucket_id: 4, bucket_name: "Unknown", count: 0 },
  { bucket_id: 5, bucket_name: "Test Logic", count: 0 },
  { bucket_id: 6, bucket_name: "Timeouts", count: 0 },
];

const inputClass =
  "rounded-md border border-border bg-background px-3 py-2 text-sm flex-1 min-w-[140px] max-w-full";

export default function DashboardPage() {
  const { days } = useTimePeriod();
  const [summary, setSummary] = useState<Summary>(FALLBACK_SUMMARY);
  const [volume, setVolume] = useState<BucketVolume[]>(FALLBACK_VOLUME);
  const [progress, setProgress] = useState<TriageProgressDay[]>([]);
  const [exportData, setExportData] = useState<ExportData | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const [logUrl, setLogUrl] = useState("");
  const [logCycleId, setLogCycleId] = useState("");
  const [discoverUrl, setDiscoverUrl] = useState("");
  const [discoverCycleId, setDiscoverCycleId] = useState("");
  const [discoverFeature, setDiscoverFeature] = useState("");
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestNote, setIngestNote] = useState<string | null>(null);
  const [ingestErr, setIngestErr] = useState<string | null>(null);

  const selectedRunRef = useRef<string | null>(null);
  selectedRunRef.current = selectedRun;

  const loadAll = useCallback(
    async (preferIdentifier?: string | null) => {
      setIsLoading(true);
      setError(null);
      try {
        const [s, v, p, runList] = await Promise.all([
          getSummary(days),
          getVolumeByBucket(days),
          getTriageProgress(days),
          listRuns(),
        ]);
        setSummary(s);
        setVolume(v);
        setProgress(p);
        setRuns(runList);

        const current = selectedRunRef.current;
        let pick: string | null = null;
        if (
          preferIdentifier &&
          runList.some((r) => r.identifier === preferIdentifier)
        ) {
          pick = preferIdentifier;
        } else if (
          current &&
          runList.some((r) => r.identifier === current)
        ) {
          pick = current;
        } else {
          pick = runList[0]?.identifier ?? null;
        }
        if (pick !== current) {
          setSelectedRun(pick);
        }

        if (pick) {
          const ex = await getExportDataAll(pick);
          setExportData(ex);
        } else {
          setExportData(null);
        }
        setLastUpdated(new Date().toISOString());
      } catch (e) {
        setError(e instanceof Error ? e : new Error("Failed to load data"));
      } finally {
        setIsLoading(false);
      }
    },
    [days]
  );

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const loadExportForRun = useCallback(async (identifier: string | null) => {
    if (!identifier) {
      setExportData(null);
      return;
    }
    try {
      const ex = await getExportDataAll(identifier);
      setExportData(ex);
    } catch (e) {
      setError(
        e instanceof Error ? e : new Error("Failed to load export for run")
      );
    }
  }, []);

  const handleTriageLogUrl = async () => {
    if (!logUrl.trim()) {
      setIngestErr("Enter a log URL.");
      return;
    }
    setIngestBusy(true);
    setIngestErr(null);
    setIngestNote(null);
    try {
      const res = await triageLogUrl(
        logUrl,
        logCycleId.trim() ? logCycleId : null
      );
      setIngestNote(
        `Triage ${res.status} — cycle “${res.run_id}”. Dashboard refreshed.`
      );
      await loadAll(res.run_id);
    } catch (e) {
      setIngestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setIngestBusy(false);
    }
  };

  const handleDiscover = async () => {
    if (!discoverUrl.trim() || !discoverCycleId.trim()) {
      setIngestErr("Enter a base URL and cycle id for discover.");
      return;
    }
    setIngestBusy(true);
    setIngestErr(null);
    setIngestNote(null);
    try {
      const res = await triageDiscover(
        discoverUrl,
        discoverCycleId,
        discoverFeature.trim() ? discoverFeature : null
      );
      setIngestNote(
        `Discover OK — ${res.ingested} test(s) in “${res.run_identifier}”. Dashboard refreshed.`
      );
      await loadAll(res.run_identifier);
    } catch (e) {
      setIngestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setIngestBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card/30 px-3 py-3 space-y-3">
        <p className="text-xs text-muted-foreground">
          Ingest writes require the same{" "}
          <code className="text-[11px]">NEXT_PUBLIC_ART_API_KEY</code> as the
          API when the server sets{" "}
          <code className="text-[11px]">ART_API_KEY</code>.
        </p>

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <input
            type="url"
            className={inputClass}
            placeholder="Log URL (JSON state dump)"
            value={logUrl}
            onChange={(e) => setLogUrl(e.target.value)}
            disabled={ingestBusy}
          />
          <input
            type="text"
            className={inputClass}
            placeholder="Cycle id (optional)"
            value={logCycleId}
            onChange={(e) => setLogCycleId(e.target.value)}
            disabled={ingestBusy}
          />
          <Button
            type="button"
            size="sm"
            disabled={ingestBusy}
            onClick={() => void handleTriageLogUrl()}
          >
            Triage log URL
          </Button>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <input
            type="url"
            className={inputClass}
            placeholder="Base URL to crawl (log tree)"
            value={discoverUrl}
            onChange={(e) => setDiscoverUrl(e.target.value)}
            disabled={ingestBusy}
          />
          <input
            type="text"
            className={inputClass}
            placeholder="Cycle id"
            value={discoverCycleId}
            onChange={(e) => setDiscoverCycleId(e.target.value)}
            disabled={ingestBusy}
          />
          <input
            type="text"
            className={inputClass}
            placeholder="Feature (optional)"
            value={discoverFeature}
            onChange={(e) => setDiscoverFeature(e.target.value)}
            disabled={ingestBusy}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={ingestBusy}
            onClick={() => void handleDiscover()}
          >
            Discover &amp; triage
          </Button>
        </div>

        {ingestNote && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400">
            {ingestNote}
          </p>
        )}
        {ingestErr && (
          <p className="text-xs text-destructive">{ingestErr}</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 px-1">
        <label className="text-sm font-medium text-muted-foreground">
          Test run / cycle
        </label>
        <select
          className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium min-w-[200px]"
          value={selectedRun ?? ""}
          onChange={(e) => {
            const v = e.target.value || null;
            setSelectedRun(v);
            void loadExportForRun(v);
          }}
          disabled={runs.length === 0}
        >
          {runs.length === 0 ? (
            <option value="">No runs yet</option>
          ) : (
            runs.map((r) => (
              <option key={r.id} value={r.identifier}>
                {r.identifier}
              </option>
            ))
          )}
        </select>
      </div>
      <DashboardShell
        summary={summary}
        volumeData={volume}
        progressData={progress}
        exportData={exportData}
        isLoading={isLoading}
        error={error}
        onRefresh={() => void loadAll()}
        lastUpdated={lastUpdated}
      />
    </div>
  );
}
