"use client";

import { useEffect, useState } from "react";
import type { HealthCheckResponse } from "@repo/types";

export function HealthStatusBadge() {
  const [status, setStatus] = useState<string>("checking...");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data: HealthCheckResponse) => {
        setStatus(data.status === "ok" ? "API Live" : "API Degraded");
      })
      .catch(() => setStatus("API Offline"));
  }, []);

  return (
    <div className="flex items-center gap-2 text-xs font-mono text-muted">
      <span className={`w-2 h-2 rounded-full ${status === "API Live" ? "bg-success" : "bg-warning"}`} />
      <span>{status}</span>
    </div>
  );
}
