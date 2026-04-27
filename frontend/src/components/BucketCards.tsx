"use client";

import { Card } from "@tremor/react";
import type { BucketVolume } from "@/lib/api";
import {
  User,
  Server,
  Bug,
  HelpCircle,
  FlaskConical,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";

const BUCKET_STYLE: Record<
  number,
  { icon: typeof Bug; colorClass: string }
> = {
  1: { icon: User, colorClass: "bg-amber-500" },
  2: { icon: Server, colorClass: "bg-cyan-500" },
  3: { icon: Bug, colorClass: "bg-rose-500" },
  4: { icon: HelpCircle, colorClass: "bg-slate-500" },
  5: { icon: FlaskConical, colorClass: "bg-violet-500" },
  6: { icon: Clock, colorClass: "bg-orange-500" },
};

interface Props {
  data: BucketVolume[];
  selectedBucket: number | null;
  onSelect: (id: number) => void;
}

export default function BucketCards({ data, selectedBucket, onSelect }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
      {data.map((b) => {
        const style = BUCKET_STYLE[b.bucket_id] ?? BUCKET_STYLE[4];
        const isActive = selectedBucket === b.bucket_id;
        const Icon = style.icon;
        return (
          <Card
            key={b.bucket_id}
            className={cn(
              "cursor-pointer p-4 transition-all duration-200",
              isActive && "ring-2 ring-ring"
            )}
            onClick={() => onSelect(b.bucket_id)}
          >
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg mb-3",
                style.colorClass
              )}
            >
              <Icon className="h-5 w-5 text-white" />
            </div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              {b.bucket_name}
            </p>
            <p
              className={cn(
                "text-2xl font-bold mt-1",
                b.count > 0 ? "text-foreground" : "text-muted-foreground/30"
              )}
            >
              {b.count}
            </p>
          </Card>
        );
      })}
    </div>
  );
}
