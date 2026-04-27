"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  AlertTriangle,
  BarChart3,
  Settings,
  Bug,
  Activity,
  FileText,
  HelpCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  section: string;
  badge?: boolean;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard, section: "DASHBOARD" },
  { href: "/attention", label: "Attention", icon: AlertTriangle, section: "DASHBOARD", badge: true },
  { href: "#", label: "Analytics", icon: BarChart3, section: "ANALYTICS", disabled: true },
  { href: "#", label: "Buckets", icon: Bug, section: "ANALYTICS", disabled: true },
  { href: "#", label: "Trends", icon: Activity, section: "ANALYTICS", disabled: true },
  { href: "#", label: "Reports", icon: FileText, section: "REPORTS", disabled: true },
  { href: "#", label: "Settings", icon: Settings, section: "SYSTEM", disabled: true },
];

const BOTTOM_NAV: NavItem[] = [
  { href: "#", label: "Help & Support", icon: HelpCircle, section: "", disabled: true },
];

export default function Sidebar() {
  const pathname = usePathname();
  const sections = Array.from(new Set(NAV_ITEMS.map((n) => n.section)));

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-16 items-center border-b border-border px-4 gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground flex-shrink-0">
          <Activity className="h-5 w-5" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-semibold">ARTs v1.0</span>
          <span className="text-xs text-muted-foreground">Failure Analytics</span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <div className="space-y-6">
          {sections.map((section) => (
            <div key={section} className="space-y-1">
              <h4 className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                {section}
              </h4>
              <ul className="flex flex-col gap-1">
                {NAV_ITEMS.filter((n) => n.section === section).map((item) => {
                  const isActive = pathname === item.href;
                  const Icon = item.icon;

                  if (item.disabled) {
                    return (
                      <li key={item.label}>
                        <div
                          className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground/50 cursor-not-allowed opacity-60"
                          title="Coming soon"
                        >
                          <Icon className="h-4 w-4 flex-shrink-0" />
                          <span className="text-sm">{item.label}</span>
                        </div>
                      </li>
                    );
                  }

                  return (
                    <li key={item.label}>
                      <Link
                        href={item.href}
                        className={cn(
                          "flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground transition-all",
                          "hover:text-primary hover:bg-accent",
                          isActive && "bg-accent text-primary font-medium"
                        )}
                      >
                        <Icon className="h-4 w-4 flex-shrink-0" />
                        <span className="text-sm">{item.label}</span>
                        {item.badge && (
                          <span className="ml-auto rounded-full bg-destructive w-2 h-2" />
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      <div className="border-t border-border px-3 py-4">
        <Separator className="mb-4" />
        <nav className="flex flex-col gap-1">
          {BOTTOM_NAV.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="flex items-center gap-3 rounded-lg px-3 py-2 text-muted-foreground/50 cursor-not-allowed opacity-60"
                title="Coming soon"
              >
                <Icon className="h-4 w-4" />
                <span className="text-sm font-medium">{item.label}</span>
              </div>
            );
          })}
        </nav>
        <div className="mt-4 px-3">
          <p className="text-xs text-muted-foreground">ARTs v1.0.0</p>
        </div>
      </div>
    </div>
  );
}
