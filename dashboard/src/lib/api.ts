export interface Report {
  _id?: string;
  pc_name?: string | null;
  device_id?: string | null;
  os?: {
    system?: string;
    release?: string;
    machine?: string;
    processor?: string;
    python_version?: string;
    hostname?: string;
    platform_detail?: string;
  };
  private_ip?: string;
  public_ip?: string;
  mac_address?: string;
  mac_addresses?: { interface: string; mac: string }[];
  location?: {
    ip?: string;
    city?: string;
    region?: string;
    country?: string;
    country_code?: string;
    lat?: number;
    lon?: number;
    isp?: string;
    timezone?: string;
  } | null;
  resources?: {
    cpu_count?: number;
    cpu_count_physical?: number;
    cpu_percent?: number;
    cpu_freq_mhz?: number | null;
    cpu_brand?: string | null;
    ram_total?: number;
    ram_used?: number;
    ram_available?: number;
    ram_free?: number;
    ram_percent?: number;
    ram_speed_mhz?: number | null;
    ram_type?: string | null;
    swap_total?: number;
    swap_used?: number;
    swap_percent?: number;
    battery?: {
      percent?: number;
      power_plugged?: boolean;
      seconds_left?: number | null;
    } | null;
  } | null;
  uptime?: {
    boot_time?: number;
    uptime_seconds?: number;
    by_day?: Record<string, number>;
    day_timezone?: string;
  } | null;
  disk?: {
    devices?: {
      device: string;
      total: number;
      used: number;
      free: number;
      percent: number;
    }[];
    partitions?: {
      device: string;
      mountpoint: string;
      fstype: string;
      total: number;
      used: number;
      free: number;
      percent: number;
    }[];
  } | null;
  printers?: {
    count?: number;
    usb?: { name: string; port: string; ip?: string | null; print_count?: number | null }[];
    network?: { name: string; port: string; ip?: string | null; print_count?: number | null }[];
    other?: { name: string; port: string; ip?: string | null; print_count?: number | null }[];
  } | null;
  network?: {
    bytes_sent?: number;
    bytes_recv?: number;
    send_rate_bps?: number;
    recv_rate_bps?: number;
  } | null;
  security?: {
    count?: number;
    installed?: {
      name: string;
      vendor: string;
      active?: boolean | null;
    }[];
    platform?: string;
  } | null;
  health?: {
    disks?: {
      name: string;
      device: string;
      media_type: string;
      brand?: string | null;
      smart_status?: string | null;
      internal?: boolean | null;
      health: string;
    }[];
    battery?: {
      cycle_count?: number | null;
      condition?: string | null;
      max_capacity_percent?: number | null;
      health_percent?: number | null;
    } | null;
  } | null;
  created_at?: number;
}

export interface ReportsResponse {
  total: number;
  reports: Report[];
}

export interface MachineSummary {
  key: string;
  deviceId: string | null;
  name: string;
  latest: Report;
  reports: Report[];
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  active: boolean;
  created_at?: number | null;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  api_key: string;
}

export interface Group {
  id: string;
  name: string;
  machine_keys: string[];
  created_at?: number | null;
}

export async function fetchReports(
  apiUrl: string,
  apiToken: string,
  limit = 100,
  filters?: {
    deviceId?: string;
    pcName?: string;
    fromTs?: number;
    toTs?: number;
    country?: string;
    os?: string;
    groupId?: string;
  },
): Promise<ReportsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.deviceId) params.set("device_id", filters.deviceId);
  if (filters?.pcName) params.set("pc_name", filters.pcName);
  if (filters?.fromTs != null) params.set("from_ts", String(filters.fromTs));
  if (filters?.toTs != null) params.set("to_ts", String(filters.toTs));
  if (filters?.country) params.set("country", filters.country);
  if (filters?.os) params.set("os", filters.os);
  if (filters?.groupId) params.set("group_id", filters.groupId);
  const res = await fetch(`${apiUrl}/reports?${params}`, {
    headers: { Authorization: `Bearer ${apiToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

/** Export matching reports as a CSV blob (from /reports/export). */
export async function exportReportsCsv(
  apiUrl: string,
  apiToken: string,
  filters?: {
    deviceId?: string;
    pcName?: string;
    fromTs?: number;
    toTs?: number;
    country?: string;
    os?: string;
    groupId?: string;
  },
  limit = 10000,
): Promise<Blob> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.deviceId) params.set("device_id", filters.deviceId);
  if (filters?.pcName) params.set("pc_name", filters.pcName);
  if (filters?.fromTs != null) params.set("from_ts", String(filters.fromTs));
  if (filters?.toTs != null) params.set("to_ts", String(filters.toTs));
  if (filters?.country) params.set("country", filters.country);
  if (filters?.os) params.set("os", filters.os);
  if (filters?.groupId) params.set("group_id", filters.groupId);
  const res = await fetch(`${apiUrl}/reports/export?${params}`, {
    headers: { Authorization: `Bearer ${apiToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.blob();
}

/** Encode machine key for URL path segment. */
export function encodeMachineKey(key: string): string {
  return encodeURIComponent(key);
}export function decodeMachineKey(encoded: string): string {
  return decodeURIComponent(encoded);
}

/** Build API filters to load reports for one machine key. */
export function filtersForMachineKey(key: string): {
  deviceId?: string;
  pcName?: string;
} {
  if (key.startsWith("id:")) return { deviceId: key.slice(3) };
  if (key.startsWith("name:")) return { pcName: key.slice(5) };
  if (key.startsWith("mac:")) return {};
  return { pcName: key };
}

export function machineName(r: Report): string {
  return r.pc_name || r.os?.hostname || r.public_ip || "Unknown PC";
}

/** Highest physical-device disk usage % on a report (0 if unknown). */
export function maxDiskPercent(r: Report): number {
  const devices = r.disk?.devices ?? [];
  if (!devices.length) return 0;
  return Math.max(0, ...devices.map((d) => d.percent ?? 0));
}

/** Total bytes transferred since boot (sent + recv). */
export function networkTotalBytes(r: Report): number {
  return (r.network?.bytes_sent ?? 0) + (r.network?.bytes_recv ?? 0);
}

export type MachineSortKey =
  | "last_seen"
  | "cpu"
  | "ram"
  | "disk"
  | "network";

export function sortMachines(
  machines: MachineSummary[],
  sort: MachineSortKey,
): MachineSummary[] {
  const copy = machines.slice();
  const metric = (m: MachineSummary): number => {
    const r = m.latest;
    switch (sort) {
      case "cpu":
        return r.resources?.cpu_percent ?? 0;
      case "ram":
        return r.resources?.ram_percent ?? 0;
      case "disk":
        return maxDiskPercent(r);
      case "network":
        return networkTotalBytes(r);
      case "last_seen":
      default:
        return r.created_at ?? 0;
    }
  };
  copy.sort((a, b) => metric(b) - metric(a));
  return copy;
}

function normalizeMac(mac?: string | null): string | null {
  if (!mac) return null;
  const cleaned = mac.toLowerCase().replace(/[^0-9a-f]/g, "");
  if (cleaned.length < 12) return null;
  if (/^0+$/.test(cleaned) || /^f+$/.test(cleaned)) return null;
  return cleaned;
}

function nameKey(r: Report): string | null {
  const name = (r.pc_name || r.os?.hostname || "").trim().toLowerCase();
  return name || null;
}

function reportMacs(r: Report): string[] {
  const out = new Set<string>();
  const primary = normalizeMac(r.mac_address);
  if (primary) out.add(primary);
  for (const iface of r.mac_addresses ?? []) {
    const mac = normalizeMac(iface.mac);
    if (mac) out.add(mac);
  }
  return [...out];
}

/** Provisional identity: device_id > MAC > name > report id. */
export function machineKey(r: Report): string {
  if (r.device_id) return `id:${r.device_id}`;
  const mac = normalizeMac(r.mac_address) ?? reportMacs(r)[0];
  if (mac) return `mac:${mac}`;
  const name = nameKey(r);
  if (name) return `name:${name}`;
  return `anon:${r._id || "unknown"}`;
}

type GroupMeta = {
  key: string;
  reports: Report[];
  deviceId: string | null;
  macs: Set<string>;
  names: Set<string>;
};

function groupScore(m: GroupMeta): number {
  if (m.deviceId || m.key.startsWith("id:")) return 3;
  if (m.key.startsWith("mac:") || m.macs.size > 0) return 2;
  return 1;
}

function shouldMerge(a: GroupMeta, b: GroupMeta): boolean {
  if (a.deviceId && b.deviceId && a.deviceId === b.deviceId) return true;
  for (const mac of a.macs) {
    if (b.macs.has(mac)) return true;
  }
  for (const name of a.names) {
    if (b.names.has(name)) return true;
  }
  return false;
}

/**
 * Group reports into one fleet row per physical PC.
 * Prefers device_id, then MAC, then name; merges overlapping identities
 * so old reports (no device_id) collapse into newer ones.
 */
export function groupMachines(reports: Report[]): MachineSummary[] {
  const buckets = new Map<string, Report[]>();
  for (const r of reports) {
    const key = machineKey(r);
    const list = buckets.get(key);
    if (list) list.push(r);
    else buckets.set(key, [r]);
  }

  const metas: GroupMeta[] = [...buckets.entries()].map(([key, reps]) => {
    const macs = new Set<string>();
    const names = new Set<string>();
    let deviceId: string | null = null;
    for (const r of reps) {
      if (r.device_id) deviceId = r.device_id;
      for (const mac of reportMacs(r)) macs.add(mac);
      const name = nameKey(r);
      if (name) names.add(name);
    }
    return { key, reports: reps, deviceId, macs, names };
  });

  const parent = metas.map((_, i) => i);
  const find = (i: number): number => {
    if (parent[i] !== i) parent[i] = find(parent[i]);
    return parent[i];
  };
  const union = (i: number, j: number) => {
    const ri = find(i);
    const rj = find(j);
    if (ri === rj) return;
    if (groupScore(metas[ri]) >= groupScore(metas[rj])) parent[rj] = ri;
    else parent[ri] = rj;
  };

  for (let i = 0; i < metas.length; i++) {
    for (let j = i + 1; j < metas.length; j++) {
      if (shouldMerge(metas[i], metas[j])) union(i, j);
    }
  }

  const merged = new Map<number, GroupMeta>();
  for (let i = 0; i < metas.length; i++) {
    const root = find(i);
    const src = metas[i];
    const existing = merged.get(root);
    if (!existing) {
      merged.set(root, {
        key: src.key,
        reports: [...src.reports],
        deviceId: src.deviceId,
        macs: new Set(src.macs),
        names: new Set(src.names),
      });
      continue;
    }
    existing.reports.push(...src.reports);
    existing.deviceId = existing.deviceId || src.deviceId;
    for (const mac of src.macs) existing.macs.add(mac);
    for (const name of src.names) existing.names.add(name);
    if (groupScore(src) > groupScore(existing)) existing.key = src.key;
    if (src.deviceId) {
      existing.deviceId = src.deviceId;
      existing.key = `id:${src.deviceId}`;
    }
  }

  return [...merged.values()]
    .map((m) => {
      const sorted = m.reports
        .slice()
        .sort((a, b) => (a.created_at ?? 0) - (b.created_at ?? 0));
      const latest = sorted[sorted.length - 1]!;
      const deviceId = m.deviceId || latest.device_id || null;
      return {
        key: deviceId ? `id:${deviceId}` : m.key,
        deviceId,
        name: machineName(latest),
        latest,
        reports: sorted,
      };
    })
    .sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
    );
}

export function fmtBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = bytes;
  let i = 0;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i += 1;
  }
  return `${size.toFixed(size >= 100 || i === 0 ? 0 : 2)} ${units[i]}`;
}

export function fmtPercent(p?: number): string {
  return p === undefined || p === null ? "—" : `${p.toFixed(1)}%`;
}

export function fmtTime(ts?: number): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

export function fmtRelative(ts?: number): string {
  if (!ts) return "—";
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

export function fmtRate(bps?: number): string {
  if (bps === undefined || bps === null) return "—";
  return `${fmtBytes(bps)}/s`;
}

export function fmtUptime(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/** Battery time-left label (e.g. "3h 12m"). */
export function fmtBatteryTime(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return "Unknown time";
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h`;
  return `${minutes}m`;
}

/** Label a UTC YYYY-MM-DD day for BD operators (Asia/Dhaka). */
export function formatUtcDayBd(utcDay: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(utcDay);
  if (!match) return utcDay;
  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  const noonUtc = Date.UTC(y, m - 1, d, 12, 0, 0);
  const bd = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Dhaka",
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(noonUtc));
  return `${utcDay} UTC · ${bd} BD`;
}

// ---- API keys ----

async function apiRequest<T>(
  apiUrl: string,
  apiToken: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore body parse errors
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function fetchApiKeys(
  apiUrl: string,
  apiToken: string,
): Promise<ApiKey[]> {
  return apiRequest(apiUrl, apiToken, "/api-keys");
}

export function createApiKey(
  apiUrl: string,
  apiToken: string,
  name: string,
): Promise<ApiKeyCreated> {
  return apiRequest(apiUrl, apiToken, "/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateApiKey(
  apiUrl: string,
  apiToken: string,
  id: string,
  changes: { name?: string; active?: boolean },
): Promise<ApiKey> {
  return apiRequest(apiUrl, apiToken, `/api-keys/${id}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function deleteApiKey(
  apiUrl: string,
  apiToken: string,
  id: string,
): Promise<void> {
  return apiRequest(apiUrl, apiToken, `/api-keys/${id}`, {
    method: "DELETE",
  });
}

// ---- groups ----

export function fetchGroups(
  apiUrl: string,
  apiToken: string,
): Promise<Group[]> {
  return apiRequest(apiUrl, apiToken, "/groups");
}

export function createGroup(
  apiUrl: string,
  apiToken: string,
  name: string,
): Promise<Group> {
  return apiRequest(apiUrl, apiToken, "/groups", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateGroup(
  apiUrl: string,
  apiToken: string,
  id: string,
  changes: { name?: string; machineKeys?: string[] },
): Promise<Group> {
  return apiRequest(apiUrl, apiToken, `/groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(changes.name !== undefined ? { name: changes.name } : {}),
      ...(changes.machineKeys !== undefined
        ? { machine_keys: changes.machineKeys }
        : {}),
    }),
  });
}

export function deleteGroup(
  apiUrl: string,
  apiToken: string,
  id: string,
): Promise<void> {
  return apiRequest(apiUrl, apiToken, `/groups/${id}`, {
    method: "DELETE",
  });
}

/** Group a machine belongs to, or null. */
export function groupOf(
  machine: MachineSummary,
  groups: Group[],
): Group | null {
  return groups.find((g) => g.machine_keys.includes(machine.key)) ?? null;
}
