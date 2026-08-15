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
      status?: "discharging" | "charging" | "full" | null;
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
  email_accounts?: {
    count?: number;
    accounts?: {
      client?: string;
      email?: string;
      username?: string | null;
      full_name?: string | null;
      protocol?: string | null;
      incoming_host?: string | null;
      incoming_port?: number | null;
      outgoing_host?: string | null;
      outgoing_port?: number | null;
      security?: string | null;
    }[];
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
      size_bytes?: number | null;
    }[];
    battery?: {
      cycle_count?: number | null;
      condition?: string | null;
      max_capacity_percent?: number | null;
      health_percent?: number | null;
    } | null;
  } | null;
  created_at?: number;
  online?: boolean;
  last_seen?: number;
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
  group_id?: string | null;
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
  subcategory_ids: string[];
  created_at?: number | null;
}

export interface User {
  id: string;
  username: string;
  role: string;
  groups: string[];
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
    subCategoryId?: string;
    diskHealth?: "healthy" | "problem";
    battery?: "has" | "none";
    batteryHealthMin?: number;
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
  if (filters?.subCategoryId) params.set("sub_category_id", filters.subCategoryId);
  if (filters?.diskHealth) params.set("disk_health", filters.diskHealth);
  if (filters?.battery) params.set("battery", filters.battery);
  if (filters?.batteryHealthMin != null)
    params.set("battery_health_min", String(filters.batteryHealthMin));
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
    subCategoryId?: string;
    diskHealth?: "healthy" | "problem";
    battery?: "has" | "none";
    batteryHealthMin?: number;
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
  if (filters?.subCategoryId) params.set("sub_category_id", filters.subCategoryId);
  if (filters?.diskHealth) params.set("disk_health", filters.diskHealth);
  if (filters?.battery) params.set("battery", filters.battery);
  if (filters?.batteryHealthMin != null)
    params.set("battery_health_min", String(filters.batteryHealthMin));
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

/** Primary MAC address for display, normalized to AA:BB:CC:DD:EE:FF. */
export function machineMac(r: Report): string | null {
  const raw = r.mac_address || r.mac_addresses?.[0]?.mac || null;
  if (!raw) return null;
  const hex = raw.toLowerCase().replace(/[^0-9a-f]/g, "");
  if (hex.length === 12) return hex.match(/.{1,2}/g)!.join(":").toUpperCase();
  return raw;
}

/** Configured email accounts on a report. */
export type EmailAccountInfo = Exclude<
  NonNullable<Report["email_accounts"]>["accounts"],
  undefined
>[number];

export function machineEmails(r: Report): EmailAccountInfo[] {
  return r.email_accounts?.accounts ?? [];
}

const CLIENT_LABELS: Record<string, string> = {
  apple_mail: "Apple Mail",
  thunderbird: "Thunderbird",
  outlook_mac: "Outlook (Mac)",
  outlook_new: "Outlook (new)",
  outlook_classic: "Outlook",
};

export function clientLabel(client?: string | null): string {
  return (client && CLIENT_LABELS[client]) || client || "Mail client";
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

function _normalizeDev(dev?: string | null): string {
  if (!dev) return "";
  return dev
    .toLowerCase()
    .replace(/^\/dev\//, "")
    .replace(/(?:s\d+)+$/, "");
}

/** Total capacity bytes on SSD or HDD physical drives (best-effort match). */
export function diskBytesByType(r: Report, type: "ssd" | "hdd"): number {
  const healthDisks = r.health?.disks ?? [];
  const media = new Map<string, string>();
  for (const d of healthDisks) {
    media.set(_normalizeDev(d.device), d.media_type);
  }
  let total = 0;
  for (const dev of r.disk?.devices ?? []) {
    if (media.get(_normalizeDev(dev.device)) === type) {
      total += dev.total ?? 0;
    }
  }
  return total;
}

export type MachineSortKey =
  | "last_seen"
  | "cpu"
  | "ram"
  | "disk"
  | "ssd"
  | "hdd"
  | "network";

export type SortOrder = "desc" | "asc";

export function sortMachines(
  machines: MachineSummary[],
  sort: MachineSortKey,
  order: SortOrder = "desc",
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
      case "ssd":
        return diskBytesByType(r, "ssd");
      case "hdd":
        return diskBytesByType(r, "hdd");
      case "network":
        return networkTotalBytes(r);
      case "last_seen":
      default:
        return r.created_at ?? 0;
    }
  };
  copy.sort((a, b) => (order === "asc" ? metric(a) - metric(b) : metric(b) - metric(a)));
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
  groupId?: string | null,
): Promise<ApiKeyCreated> {
  return apiRequest(apiUrl, apiToken, "/api-keys", {
    method: "POST",
    body: JSON.stringify({ name, group_id: groupId ?? null }),
  });
}

export function updateApiKey(
  apiUrl: string,
  apiToken: string,
  id: string,
  changes: { name?: string; active?: boolean; groupId?: string | null },
): Promise<ApiKey> {
  const body: Record<string, unknown> = { ...changes };
  if ("groupId" in changes) {
    body.group_id = changes.groupId ?? "";
  }
  delete body.groupId;
  return apiRequest(apiUrl, apiToken, `/api-keys/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function regenerateApiKey(
  apiUrl: string,
  apiToken: string,
  id: string,
): Promise<ApiKeyCreated> {
  return apiRequest(apiUrl, apiToken, `/api-keys/${id}/regenerate`, {
    method: "POST",
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

// ---- sub-categories ----

export interface SubCategory {
  id: string;
  name: string;
  group_ids: string[];
  machine_keys: string[];
  created_at?: number | null;
}

export function fetchSubCategories(
  apiUrl: string,
  apiToken: string,
): Promise<SubCategory[]> {
  return apiRequest(apiUrl, apiToken, "/sub-categories");
}

export function createSubCategory(
  apiUrl: string,
  apiToken: string,
  name: string,
  group_ids: string[],
): Promise<SubCategory> {
  return apiRequest(apiUrl, apiToken, "/sub-categories", {
    method: "POST",
    body: JSON.stringify({ name, group_ids }),
  });
}

export function updateSubCategory(
  apiUrl: string,
  apiToken: string,
  id: string,
  changes: {
    name?: string;
    groupIds?: string[];
    machineKeys?: string[];
  },
): Promise<SubCategory> {
  return apiRequest(apiUrl, apiToken, `/sub-categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(changes.name !== undefined ? { name: changes.name } : {}),
      ...(changes.groupIds !== undefined
        ? { group_ids: changes.groupIds }
        : {}),
      ...(changes.machineKeys !== undefined
        ? { machine_keys: changes.machineKeys }
        : {}),
    }),
  });
}

export function deleteSubCategory(
  apiUrl: string,
  apiToken: string,
  id: string,
): Promise<void> {
  return apiRequest(apiUrl, apiToken, `/sub-categories/${id}`, {
    method: "DELETE",
  });
}

// ---- users (super admin only) ----

export function fetchUsers(
  apiUrl: string,
  apiToken: string,
): Promise<User[]> {
  return apiRequest(apiUrl, apiToken, "/users");
}

export function createUser(
  apiUrl: string,
  apiToken: string,
  data: { username: string; password: string; role: string; groups: string[] },
): Promise<User> {
  return apiRequest(apiUrl, apiToken, "/users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateUser(
  apiUrl: string,
  apiToken: string,
  id: string,
  data: { role?: string; groups?: string[]; password?: string },
): Promise<User> {
  return apiRequest(apiUrl, apiToken, `/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteUser(
  apiUrl: string,
  apiToken: string,
  id: string,
): Promise<void> {
  return apiRequest(apiUrl, apiToken, `/users/${id}`, {
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

/** Sub-category a machine belongs to, or null. */
export function subCategoryOf(
  machine: MachineSummary,
  subCategories: SubCategory[],
): SubCategory | null {
  return (
    subCategories.find((s) => s.machine_keys.includes(machine.key)) ?? null
  );
}

/** Online status of a machine (annotated by the API from heartbeats). */
export function isOnline(m: Pick<MachineSummary, "latest">): boolean {
  return m.latest.online === true;
}

/** Print total across printer groups on a report. */
export function totalPrints(r: Report): number {
  const p = r.printers;
  if (!p) return 0;
  return (
    (p.usb?.reduce((s, x) => s + (x.print_count ?? 0), 0) ?? 0) +
    (p.network?.reduce((s, x) => s + (x.print_count ?? 0), 0) ?? 0) +
    (p.other?.reduce((s, x) => s + (x.print_count ?? 0), 0) ?? 0)
  );
}

// ---- print jobs ----

export type PrintJob = {
  _id: string;
  device_id?: string;
  pc_name?: string | null;
  printer: string;
  document: string;
  user?: string | null;
  pages?: number | null;
  completed_at?: number | null;
  created_at?: number;
};

export type PrintJobsResponse = {
  total: number;
  jobs: PrintJob[];
};

export type PrintHourBucket = {
  hour: string;
  count: number;
};

export type PrintJobsSummary = {
  hours: number;
  buckets: PrintHourBucket[];
};

export function fetchPrintJobs(
  apiUrl: string,
  apiToken: string,
  limit = 100,
): Promise<PrintJobsResponse> {
  return apiRequest(apiUrl, apiToken, `/print-jobs?limit=${limit}`);
}

export function fetchPrintSummary(
  apiUrl: string,
  apiToken: string,
  hours = 24,
): Promise<PrintJobsSummary> {
  return apiRequest(apiUrl, apiToken, `/print-jobs/summary?hours=${hours}`);
}

// ---- remote commands (restart / shutdown) ----

export type Command = {
  id: string;
  device_id?: string;
  type?: string;
  status?: string;
  requested_by?: string;
  created_at?: number;
  acked_at?: number | null;
  error?: string | null;
};

export function sendCommand(
  apiUrl: string,
  apiToken: string,
  deviceId: string,
  type: "restart" | "shutdown",
): Promise<Command> {
  return apiRequest(apiUrl, apiToken, "/commands", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId, type }),
  });
}

export type DevicePingResult = {
  connected: boolean;
  rtt_ms: number | null;
  reason?: string | null;
};

export function pingDevice(
  apiUrl: string,
  apiToken: string,
  deviceId: string,
): Promise<DevicePingResult> {
  return apiRequest(apiUrl, apiToken, "/commands/ping", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId }),
  });
}

export function fetchCommands(
  apiUrl: string,
  apiToken: string,
  deviceId?: string,
  limit = 20,
): Promise<{ total: number; commands: Command[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (deviceId) params.set("device_id", deviceId);
  return apiRequest(apiUrl, apiToken, `/commands?${params}`);
}

export function broadcastCommand(
  apiUrl: string,
  apiToken: string,
  type = "update",
): Promise<{ total: number; sent: Command[]; connected: number }> {
  return apiRequest(apiUrl, apiToken, "/commands/broadcast", {
    method: "POST",
    body: JSON.stringify({ type }),
  });
}
