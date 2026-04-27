"use client";

import { useMemo, useState, useEffect } from "react";
import { Card, Title } from "@tremor/react";
import { ExternalLink } from "lucide-react";
import { ExportButton } from "@/components/ui/export-button";
import { Button } from "@/components/ui/button";

export interface FailureRow {
  testCase: string;
  feature: string;
  message: string;
  bugId: string | null;
  logUrl: string;
  isSticky: boolean;
  isPassing: boolean;
  attemptId?: number;
  fingerprint?: string;
}

interface Props {
  rows: FailureRow[];
  title: string;
  onBugIdSave?: (
    attemptId: number,
    fingerprint: string,
    bugId: string | null
  ) => Promise<void>;
}

const EXPORT_COLUMNS = [
  { key: "testCase", label: "Test Case" },
  { key: "feature", label: "Feature" },
  { key: "message", label: "Error Signature" },
  { key: "bugId", label: "Bug ID" },
  { key: "logUrl", label: "Log URL" },
];

function BugCell({
  bugId,
  attemptId,
  fingerprint,
  onSave,
}: {
  bugId: string | null;
  attemptId?: number;
  fingerprint?: string;
  onSave?: Props["onBugIdSave"];
}) {
  const [val, setVal] = useState(bugId ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setVal(bugId ?? "");
  }, [bugId]);

  const canEdit =
    onSave && attemptId != null && fingerprint != null && fingerprint !== "";

  if (!canEdit) {
    return (
      <span
        className={`font-medium text-xs ${
          bugId && bugId !== "Unassigned"
            ? "text-blue-600 dark:text-blue-400"
            : "text-muted-foreground/50"
        }`}
      >
        {bugId || "Unassigned"}
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 max-w-[200px]">
      <input
        className="w-full rounded border border-border bg-background px-2 py-1 text-xs font-mono"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        placeholder="Bug / issue ID"
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        className="h-7 text-xs"
        disabled={saving}
        onClick={async () => {
          setSaving(true);
          try {
            await onSave(attemptId, fingerprint, val.trim() || null);
          } finally {
            setSaving(false);
          }
        }}
      >
        {saving ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}

export default function FailuresTable({
  rows,
  title,
  onBugIdSave,
}: Props) {
  const exportData = useMemo(
    () =>
      rows.map((r) => ({
        testCase: r.testCase,
        feature: r.feature,
        message: r.message,
        bugId: r.bugId || "Unassigned",
        logUrl: r.logUrl,
      })),
    [rows]
  );

  return (
    <Card className="overflow-hidden">
      <div className="px-6 py-4 border-b border-border flex justify-between items-center">
        <Title className="text-base font-semibold">{title}</Title>
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-muted-foreground bg-muted px-3 py-1 rounded-full">
            {rows.length} Issues
          </span>
          <ExportButton
            data={exportData}
            columns={EXPORT_COLUMNS}
            filename="arts-failures"
          />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs font-semibold text-muted-foreground uppercase tracking-wider border-b border-border">
            <tr>
              <th className="px-6 py-3">Test Case & Feature</th>
              <th className="px-6 py-3">Error Signature</th>
              <th className="px-6 py-3">Bug ID</th>
              <th className="px-6 py-3 text-right">Log</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-6 py-12 text-center text-muted-foreground font-medium"
                >
                  No active issues found.
                </td>
              </tr>
            ) : (
              rows.map((r, i) => (
                <tr
                  key={
                    r.attemptId != null && r.fingerprint
                      ? `${r.attemptId}-${r.fingerprint}`
                      : i
                  }
                  className="hover:bg-accent transition-colors"
                >
                  <td className="px-6 py-4">
                    <p className="font-medium text-foreground text-sm">
                      {r.testCase}
                    </p>
                    <p className="text-xs text-muted-foreground uppercase mt-0.5">
                      {r.feature}
                    </p>
                    {r.isSticky && r.isPassing && (
                      <span className="inline-block mt-1.5 text-xs font-medium text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30 px-2 py-0.5 rounded-full">
                        Passed, but Sticky PSOD
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div
                      className="font-mono text-xs bg-muted p-2 rounded-lg text-muted-foreground border border-border max-w-xl truncate"
                      title={r.message}
                    >
                      {r.message}
                    </div>
                  </td>
                  <td className="px-6 py-4 align-top">
                    <BugCell
                      bugId={r.bugId}
                      attemptId={r.attemptId}
                      fingerprint={r.fingerprint}
                      onSave={onBugIdSave}
                    />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <a
                      href={r.logUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      View
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
