"use client";

import { useState } from "react";
import { Card } from "@tremor/react";
import { AlertTriangle, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BucketVolume } from "@/lib/api";

interface Props {
  buckets: BucketVolume[];
}

export default function AttentionView({ buckets }: Props) {
  const [activeTab, setActiveTab] = useState<number>(3);

  const productBucket = buckets.find((b) => b.bucket_id === 3);
  const unknownBucket = buckets.find((b) => b.bucket_id === 4);

  const tabs = [
    {
      id: 3,
      label: "Product Bugs",
      count: productBucket?.count ?? 0,
      icon: AlertTriangle,
      colorClass: "bg-rose-500",
      description:
        "PSODs, core dumps, and firstboot failures requiring product bug filings.",
    },
    {
      id: 4,
      label: "Unknown",
      count: unknownBucket?.count ?? 0,
      icon: HelpCircle,
      colorClass: "bg-slate-500",
      description:
        "Failures that could not be automatically classified. Manual pattern extraction needed.",
    },
  ];

  const active = tabs.find((t) => t.id === activeTab)!;

  return (
    <div className="space-y-6">
      {/* Tab Selector */}
      <div className="flex gap-4">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <Card
              key={tab.id}
              className={cn(
                "cursor-pointer transition-all duration-200",
                isActive && "ring-2 ring-ring"
              )}
              onClick={() => setActiveTab(tab.id)}
            >
              <div className="flex items-center gap-3 px-2 py-1">
                <div
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-lg",
                    isActive ? tab.colorClass : "bg-muted"
                  )}
                >
                  <Icon
                    className={cn(
                      "h-4 w-4",
                      isActive ? "text-white" : "text-muted-foreground"
                    )}
                  />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {tab.label}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <span className="font-bold">{tab.count}</span> active issues
                  </p>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Detail Card */}
      <Card className="p-6">
        <div className="flex items-start gap-4 mb-6">
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-xl",
              active.colorClass
            )}
          >
            <active.icon className="h-6 w-6 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground">
              {active.label}
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              {active.description}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl bg-muted p-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Count
            </p>
            <p className="text-4xl font-bold text-foreground">
              {active.count}
            </p>
          </div>
          <div className="rounded-xl bg-muted p-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Priority
            </p>
            <span
              className={cn(
                "inline-block text-sm font-semibold px-3 py-1 rounded-full",
                active.id === 3
                  ? "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
              )}
            >
              {active.id === 3 ? "Critical" : "Needs Review"}
            </span>
            <p className="text-sm text-muted-foreground mt-3">
              {active.id === 3
                ? "These require immediate product bug filings."
                : "These need manual investigation to create new rules."}
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
