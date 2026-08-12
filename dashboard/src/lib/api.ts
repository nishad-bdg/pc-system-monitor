export interface Report {
  _id?: string;
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
  created_at?: number;
}

export interface ReportsResponse {
  total: number;
  reports: Report[];
}

export async function fetchReports(
  apiUrl: string,
  apiToken: string,
  limit = 100,
): Promise<ReportsResponse> {
  const res = await fetch(`${apiUrl}/reports?limit=${limit}`, {
    headers: { Authorization: `Bearer ${apiToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
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