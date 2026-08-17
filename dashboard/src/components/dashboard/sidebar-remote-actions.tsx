"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { fetchReports, groupMachines, MachineSummary } from "@/lib/api";
import { ConnectAllButton } from "./connect-all-button";
import { UpdateAppsButton } from "./update-apps-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const ADMIN_ROLES = new Set(["admin", "super_admin"]);

export function deviceIdsOf(
  machines: Pick<MachineSummary, "deviceId">[],
): string[] {
  return Array.from(
    new Set(
      machines
        .map((m) => m.deviceId)
        .filter((id): id is string => Boolean(id)),
    ),
  );
}

/** Connect all (admin+) and Update all apps (super_admin) in every page sidebar. */
export function SidebarRemoteActions({
  deviceIds,
}: {
  deviceIds?: string[];
}) {
  const { data: session } = useSession();
  const role = session?.user?.role ?? "";
  const apiToken = session?.user?.apiToken ?? "";
  const canRemote = ADMIN_ROLES.has(role);
  const isSuperAdmin = role === "super_admin";

  const { data } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken, 500),
    enabled: !!apiToken && canRemote && deviceIds == null,
    staleTime: 30_000,
  });

  const ids = useMemo(() => {
    if (deviceIds) return deviceIds;
    return deviceIdsOf(groupMachines(data?.reports ?? []));
  }, [deviceIds, data?.reports]);

  if (!canRemote) return null;

  return (
    <div className="space-y-2">
      <ConnectAllButton
        apiUrl={API_URL}
        apiToken={apiToken}
        deviceIds={ids}
      />
      {isSuperAdmin && (
        <UpdateAppsButton apiUrl={API_URL} apiToken={apiToken} />
      )}
    </div>
  );
}
