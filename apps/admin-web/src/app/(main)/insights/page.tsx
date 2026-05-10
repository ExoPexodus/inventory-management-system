"use client";

import { useState } from "react";
import { PageHeader, Tabs } from "@/components/ui/primitives";
import { AnalyticsView } from "@/app/(main)/analytics/AnalyticsView";
import { ReportsView } from "@/app/(main)/reports/ReportsView";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "reports", label: "Reports" },
];

export default function InsightsPage() {
  const [tab, setTab] = useState("dashboard");

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Insights"
        title="Insights"
        subtitle="Live dashboards and CSV exports for accounting and ops."
      />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      <div>
        {tab === "dashboard" && <AnalyticsView />}
        {tab === "reports" && <ReportsView />}
      </div>
    </div>
  );
}
