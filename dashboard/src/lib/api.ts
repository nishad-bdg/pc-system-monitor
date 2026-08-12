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
    ram_total?: number;
    ram_used?: number;
    ram_available?: number;
    ram_free?: number;
    ram_percent?: number;
    swap_total?: number;
    swap_used?: number;
    swap_percent?: number;
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
    usb?: { name: string; port: string }[];
    network?: { name: string; port: string }[];
    other?: { name: string; port: string }[];
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

export async function fetchReports(
  apiUrl: string,
  apiToken: string,
  limit = 100,
  filters?: { deviceId?: string; pcName?: string },
): Promise<ReportsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.deviceId) params.set("device_id", filters.deviceId);
  if (filters?.pcName) params.set("pc_name", filters.pcName);
  const res = await fetch(`${apiUrl}/reports?${params}`, {
    headers: { Authorization: `Bearer ${apiToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export function machineKey(r: Report): string {
  return r.device_id || r.pc_name || r.os?.hostname || r._id || "unknown";
}

export function machineName(r: Report): string {
  return r.pc_name || r.os?.hostname || r.public_ip || "Unknown PC";
}

/** Group reports into machines; each machine keeps reports sorted ascending by time. */
export function groupMachines(reports: Report[]): MachineSummary[] {
  const map = new Map<string, MachineSummary>();
  for (const r of reports) {
    const key = machineKey(r);
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        key,
        deviceId: r.device_id ?? null,
        name: machineName(r),
        latest: r,
        reports: [r],
      });
      continue;
    }
    existing.reports.push(r);
    if ((r.created_at ?? 0) >= (existing.latest.created_at ?? 0)) {
      existing.latest = r;
      existing.name = machineName(r);
      existing.deviceId = r.device_id ?? existing.deviceId;
    }
  }
  return Array.from(map.values()).sort((a, b) =>
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
