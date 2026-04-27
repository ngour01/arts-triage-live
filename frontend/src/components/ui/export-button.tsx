"use client";

import { useState, useCallback } from "react";
import { Download, FileSpreadsheet, Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface ExportButtonProps {
  data: Record<string, unknown>[];
  columns: { key: string; label: string }[];
  filename?: string;
  disabled?: boolean;
}

function generateCsv(
  data: Record<string, unknown>[],
  columns: { key: string; label: string }[]
): string {
  const header = columns.map((c) => c.label).join(",");
  const rows = data.map((row) =>
    columns
      .map((c) => {
        const val = String(row[c.key] ?? "");
        if (val.includes(",") || val.includes('"') || val.includes("\n")) {
          return `"${val.replace(/"/g, '""')}"`;
        }
        return val;
      })
      .join(",")
  );
  return [header, ...rows].join("\n");
}

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function ExportButton({
  data,
  columns,
  filename = "export",
  disabled = false,
}: ExportButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<"idle" | "success">("idle");

  const date = new Date().toISOString().split("T")[0];
  const fullName = `${filename}-${date}`;

  const flash = useCallback(() => {
    setStatus("success");
    setTimeout(() => {
      setStatus("idle");
      setIsOpen(false);
    }, 1000);
  }, []);

  const handleCsv = useCallback(() => {
    const csv = generateCsv(data, columns);
    downloadFile(csv, `${fullName}.csv`, "text/csv;charset=utf-8;");
    flash();
  }, [data, columns, fullName, flash]);

  const handleExcel = useCallback(() => {
    const csv = "\uFEFF" + generateCsv(data, columns);
    downloadFile(csv, `${fullName}.csv`, "text/csv;charset=utf-8;");
    flash();
  }, [data, columns, fullName, flash]);

  const handleClipboard = useCallback(async () => {
    const csv = generateCsv(data, columns);
    const tsv = csv
      .split("\n")
      .map((r) => r.split(",").join("\t"))
      .join("\n");
    try {
      await navigator.clipboard.writeText(tsv);
      flash();
    } catch {
      /* clipboard not available */
    }
  }, [data, columns, flash]);

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || data.length === 0}
          className="gap-2"
        >
          <Download className="h-4 w-4" />
          Export
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-48 p-2" align="end">
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground px-2 py-1 uppercase tracking-wide">
            Export As
          </p>
          <Button variant="ghost" size="sm" className="justify-start h-9 px-2" onClick={handleCsv}>
            {status === "success" ? <Check className="h-4 w-4 mr-2 text-green-500" /> : <FileSpreadsheet className="h-4 w-4 mr-2" />}
            CSV File
          </Button>
          <Button variant="ghost" size="sm" className="justify-start h-9 px-2" onClick={handleExcel}>
            {status === "success" ? <Check className="h-4 w-4 mr-2 text-green-500" /> : <FileSpreadsheet className="h-4 w-4 mr-2" />}
            Excel (CSV)
          </Button>
          <div className="border-t border-border my-1" />
          <Button variant="ghost" size="sm" className="justify-start h-9 px-2" onClick={handleClipboard}>
            {status === "success" ? <Check className="h-4 w-4 mr-2 text-green-500" /> : <Copy className="h-4 w-4 mr-2" />}
            Copy to Clipboard
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
